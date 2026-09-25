"""Own only the processes launched for this run; never kill by image name."""

import hashlib
import os
import socket
import subprocess
from pathlib import Path

from .scenario import enu_to_geo


class SITLProcesses:
    def __init__(self, binary, template, run_dir, scenario, base_port=19100):
        self.binary = Path(binary).resolve()
        self.template = Path(template).resolve()
        self.run_dir = Path(run_dir)
        self.scenario = scenario
        self.base_port = base_port
        self.processes = []
        self.logs = []
        self.instances = []

    def start(self):
        if not self.binary.is_file() or not self.template.is_file():
            raise FileNotFoundError("SITL executable or parameter template is missing")
        if not 1024 <= self.base_port <= 65000 - 10 * len(self.scenario["vehicles"]):
            raise ValueError("base port is outside the usable range")
        for index, vehicle in enumerate(self.scenario["vehicles"]):
            port = self.base_port + index * 10
            # Check serial TCP listeners and explicitly assigned simulation UDP ports.
            for offset in range(10):
                for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                    with socket.socket(socket.AF_INET, kind) as probe:
                        if os.name == "nt":
                            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                        probe.bind(("127.0.0.1", port + offset))
        try:
            for index, vehicle in enumerate(self.scenario["vehicles"]):
                port = self.base_port + index * 10
                directory = self.run_dir / "sitl" / vehicle["id"]
                directory.mkdir(parents=True, exist_ok=False)
                params = self.template.read_text(encoding="utf-8")
                params += f"\nSYSID_THISMAV {vehicle['sysid']}\nLOG_DISARMED 1\n"
                (directory / "defaults.parm").write_text(params, encoding="utf-8")
                lat, lon = enu_to_geo(vehicle["east_m"], vehicle["north_m"], self.scenario["origin"])
                home = f"{lat:.10f},{lon:.10f},{self.scenario['origin']['alt_msl_m']},{vehicle['heading_deg']}"
                args = [str(self.binary), "--model", "quad", "--home", home,
                        # This bundled build does not offset an explicit base-port
                        # with --instance, despite the wording of its --help output.
                        "--base-port", str(port), "--instance", str(index), "--uartA", "tcp:0",
                        "--rc-in-port", str(port + 8), "--sim-port-in", str(port + 6),
                        "--sim-port-out", str(port + 7), "--irlock-port", str(port + 9),
                        "--defaults", "defaults.parm", "--speedup", "1", "--wipe", "--disable-fgview"]
                log = (directory / "console.log").open("wb")
                self.logs.append(log)
                process = subprocess.Popen(args, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.processes.append(process)
                self.instances.append(dict(id=vehicle["id"], sysid=vehicle["sysid"], pid=process.pid,
                                           url=f"tcp:127.0.0.1:{port}", argv=args,
                                           directory=str(directory.resolve())))
        except BaseException:
            self.close()
            raise
        return self.instances

    def check(self):
        for process, instance in zip(self.processes, self.instances):
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"{instance['id']} SITL exited ({code}); see {instance['directory']}/console.log")

    def metadata(self):
        return dict(binary=str(self.binary), sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                    instances=self.instances, speedup=1)

    def close(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in self.logs:
            log.close()
