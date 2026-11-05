"""V8-15 第 4 部分：Windows 内存及核数采集（指令 4.2）；不装依赖、不改系统设置。

- 进程生涯峰值工作集：psutil（环境已有 7.0.0）的 memory_info().peak_wset；没有 psutil 时用 ctypes 调
  psapi.GetProcessMemoryInfo（PROCESS_MEMORY_COUNTERS.PeakWorkingSetSize）。worker 在结束前自报，按 PID 取最大值，
  不把各 worker 峰值相加冒充全机峰值。
- 全机已用物理内存：total − available（psutil.virtual_memory 或 kernel32.GlobalMemoryStatusEx 的
  ullTotalPhys − ullAvailPhys）。父进程后台线程按 1 s 采样（本稿测量协议的执行设置，不参与物理/算法判定），
  派发前、每次完成与批次结束另取样。报告"采样峰值"，不声称捕获采样间所有瞬时尖峰。
- 核数：PowerShell Get-CimInstance Win32_Processor 的 NumberOfCores / NumberOfLogicalProcessors（逐插槽列出）。
"""
import ctypes
import json
import os
import subprocess
import threading
import time

try:
    import psutil
except ImportError:          # 不安装：退回 ctypes
    psutil = None

SAMPLE_INTERVAL_S = 1.0      # 本稿测量协议（指令 4.2）


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class _MSE(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def process_memory():
    """本进程 {pid, peak_working_set_bytes, working_set_bytes, source}；不可得时字段为 None 并给原因。"""
    pid = os.getpid()
    if psutil is not None:
        mi = psutil.Process(pid).memory_info()
        return {"pid": pid, "peak_working_set_bytes": int(getattr(mi, "peak_wset", 0)) or None,
                "working_set_bytes": int(getattr(mi, "wset", mi.rss)), "source": "psutil.memory_info"}
    try:
        k32 = ctypes.WinDLL("kernel32")
        ps = ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        c = _PMC()
        c.cb = ctypes.sizeof(_PMC)
        ok = ps.GetProcessMemoryInfo(ctypes.c_void_p(k32.GetCurrentProcess()), ctypes.byref(c), c.cb)
        if not ok:
            return {"pid": pid, "peak_working_set_bytes": None, "working_set_bytes": None,
                    "source": "GetProcessMemoryInfo", "error": f"返回 0，GetLastError={ctypes.GetLastError()}"}
        return {"pid": pid, "peak_working_set_bytes": int(c.PeakWorkingSetSize),
                "working_set_bytes": int(c.WorkingSetSize), "source": "GetProcessMemoryInfo"}
    except OSError as exc:
        return {"pid": pid, "peak_working_set_bytes": None, "working_set_bytes": None, "source": None,
                "error": repr(exc)}


def system_memory():
    """{total_bytes, used_bytes(total−available), fraction, source}。"""
    if psutil is not None:
        vm = psutil.virtual_memory()
        return {"total_bytes": int(vm.total), "used_bytes": int(vm.total - vm.available),
                "fraction": (vm.total - vm.available) / vm.total, "source": "psutil.virtual_memory"}
    m = _MSE()
    m.dwLength = ctypes.sizeof(_MSE)
    if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(m)):
        return {"total_bytes": None, "used_bytes": None, "fraction": None, "source": "GlobalMemoryStatusEx",
                "error": f"GetLastError={ctypes.GetLastError()}"}
    used = m.ullTotalPhys - m.ullAvailPhys
    return {"total_bytes": int(m.ullTotalPhys), "used_bytes": int(used), "fraction": used / m.ullTotalPhys,
            "source": "GlobalMemoryStatusEx"}


class SystemSampler:
    """父进程后台线程：每 SAMPLE_INTERVAL_S 秒取一次全机已用物理内存；mark(label) 另取事件样本。"""

    def __init__(self, interval_s=SAMPLE_INTERVAL_S):
        self.interval_s = float(interval_s)
        self.samples = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._th = None

    def _take(self, label):
        s = system_memory()
        with self._lock:
            self.samples.append({"t": time.time(), "label": label, "used_bytes": s["used_bytes"],
                                 "total_bytes": s["total_bytes"], "fraction": s["fraction"]})

    def _run(self):
        while not self._stop.wait(self.interval_s):
            self._take("periodic")

    def start(self):
        self._take("start")
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        return self

    def mark(self, label):
        self._take(label)

    def stop(self):
        self._take("end")
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=5)
        return self.summary()

    def summary(self):
        with self._lock:
            ok = [s for s in self.samples if s["fraction"] is not None]
            periodic = [s for s in ok if s["label"] == "periodic"]
            if not ok:
                return {"samples": len(self.samples), "peak_fraction": None, "reason": "系统内存不可得"}
            peak = max(ok, key=lambda s: s["fraction"])
            return {"interval_s": self.interval_s, "samples": len(ok), "periodic_samples": len(periodic),
                    "event_samples": len(ok) - len(periodic), "peak_fraction": peak["fraction"],
                    "peak_used_bytes": peak["used_bytes"], "total_bytes": peak["total_bytes"],
                    "peak_label": peak["label"], "start_fraction": ok[0]["fraction"], "end_fraction": ok[-1]["fraction"],
                    "note": "1 s 采样峰值；不声称捕获采样间瞬时尖峰；包含用户其他进程占用（不扣除）"}


def cpu_info():
    """Win32_Processor 的物理/逻辑核（逐插槽）。不可得时返回原因。"""
    cmd = ["pwsh", "-NoProfile", "-Command",
           "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,SocketDesignation"
           " | ConvertTo-Json -Compress"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
        rows = json.loads(out)
        rows = rows if isinstance(rows, list) else [rows]
        return {"sockets": rows, "physical_cores": sum(int(r["NumberOfCores"]) for r in rows),
                "logical_processors": sum(int(r["NumberOfLogicalProcessors"]) for r in rows),
                "source": "Win32_Processor"}
    except Exception as exc:          # 不猜测
        return {"sockets": None, "physical_cores": None, "logical_processors": None, "error": repr(exc)}
