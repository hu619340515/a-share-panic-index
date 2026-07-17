#!/usr/bin/env python3
"""Hermes 图表技能命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent
for path in (SCRIPT_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from a_share_panic_index.charting import run_chart


class CliArgumentError(ValueError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="生成A股恐慌指数综合图")
    subparsers = parser.add_subparsers(dest="command")
    chart = subparsers.add_parser("chart", help="生成最近交易日综合图")
    chart.add_argument(
        "--days", "-d", type=int, default=120, help="显示最近N个交易日（默认120）"
    )
    chart.add_argument("--output", "-o", default="reports/panic_index.png")
    chart.add_argument("--date", type=parse_date, help="指定截止交易日 YYYY-MM-DD")
    chart.add_argument("--force-refresh", action="store_true", help="强制重建历史数据")
    chart.add_argument("--config", help="配置文件路径")
    chart.add_argument("--database", help="SQLite数据库路径")
    return parser


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期格式必须为 YYYY-MM-DD") from error


def parse_now() -> datetime | None:
    value = os.environ.get("PANIC_INDEX_NOW")
    return datetime.fromisoformat(value) if value else None


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    configure_utf8()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliArgumentError as error:
        emit(
            {
                "schema_version": "1.0",
                "ok": False,
                "status": "argument_error",
                "exit_code": 2,
                "chart_path": None,
                "errors": [{"type": type(error).__name__, "message": str(error)}],
            }
        )
        return 2
    if args.command is None:
        parser.print_help(sys.stderr)
        return 0
    return run_chart(args, now=parse_now())


if __name__ == "__main__":
    raise SystemExit(main())
