"""Launch the optional, offline PyQt replay and task preview application."""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="Task/scene JSON or completed run directory")
    args = parser.parse_args()
    try:
        from replay_viewer.window import launch
    except ImportError as exc:
        print(f"可视化依赖不可用：{exc}\n请使用已包含 PyQt5、pyqtgraph、numpy 的项目 llm 环境。", file=sys.stderr)
        return 2
    return launch(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
