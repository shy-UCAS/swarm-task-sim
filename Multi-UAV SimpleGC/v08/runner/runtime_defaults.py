"""运行时默认值（V8-15 第 4 部分实测选定；只保存进程数，不含任何算法参数）。

DEFAULT_WORKERS = 24：本机（AMD Ryzen 9 9950X3D，16 物理核 / 32 逻辑处理器，63.65 GB）上，同一组 40 个中等耗时
合同分别以 8/16/24 进程运行，P0-3 三档逐字节一致；按"逐合同耗时比中位数 → 吞吐量 W/I；全机已用物理内存采样峰值
≤ 60%；24 相对 16 增益 < 10% 时取 16"选定。测量提交 52f3915；名单 docs/v08/V8-15/part4/selection.json，
选择结果 docs/v08/V8-15/part4/worker_choice.json，性能表 docs/v08/V8-15/part4/part4_table.json（路径相对仓库根）。
换机器后不自动适用。本模块导入时不读文件。
"""
DEFAULT_WORKERS = 24
