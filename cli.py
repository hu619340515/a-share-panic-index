#!/usr/bin/env python3
"""兼容入口，实际命令实现在 scripts/cli.py。"""

from scripts.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
