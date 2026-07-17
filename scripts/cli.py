#!/usr/bin/env python3
"""A股恐慌指数命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from a_share_panic_index.config import Settings
from a_share_panic_index.logging_utils import configure_logging
from a_share_panic_index.runner import DailyRunner


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
    parser = JsonArgumentParser(description="A股恐慌指数自动化工具")
    subparsers = parser.add_subparsers(dest="command")

    for command, help_text in (("daily", "单次生成结构化日报"), ("current", "显示当前恐慌指数")):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--date", type=parse_date, help="指定交易日 YYYY-MM-DD")
        command_parser.add_argument("--force-refresh", action="store_true", help="强制重建历史窗口")
        command_parser.add_argument("--config", help="配置文件路径")
        command_parser.add_argument("--database", help="SQLite数据库路径")

    history_parser = subparsers.add_parser("history", help="查看历史数据")
    history_parser.add_argument("--days", "-d", type=int, default=30)

    chart_parser = subparsers.add_parser("chart", help="生成图表")
    chart_parser.add_argument(
        "--days", "-d", type=int, default=120, help="显示最近N个交易日（默认120）"
    )
    chart_parser.add_argument(
        "--type",
        "-t",
        choices=["simple", "comprehensive", "comparison"],
        default="comprehensive",
    )
    chart_parser.add_argument("--output", "-o", default="panic_chart.png")
    chart_parser.add_argument("--date", type=parse_date, help="刷新到指定交易日 YYYY-MM-DD")
    chart_parser.add_argument("--force-refresh", action="store_true", help="强制重建历史窗口")
    chart_parser.add_argument("--config", help="配置文件路径")
    chart_parser.add_argument("--database", help="SQLite数据库路径")

    subparsers.add_parser("backtest", help="运行回测")
    subparsers.add_parser("alert", help="测试告警")
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("action", choices=["get", "set", "list"])
    config_parser.add_argument("key", nargs="?")
    config_parser.add_argument("value", nargs="?")
    subparsers.add_parser("monitor", help="监控模式")
    return parser


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期格式必须为 YYYY-MM-DD") from error


def parse_now() -> datetime | None:
    value = os.environ.get("PANIC_INDEX_NOW")
    return datetime.fromisoformat(value) if value else None


def run_daily(args, human: bool = False) -> int:
    run_id = str(uuid4())
    try:
        settings = Settings(args.config)
        database_config = settings.section("database")
        database_path = (
            Path(args.database).expanduser().resolve()
            if args.database
            else settings.resolve_path(database_config.get("path", "./data_cache/panic_index.db"))
        )
        logging_config = settings.section("logging")
        log_directory = settings.resolve_path(logging_config.get("directory", "./logs"))
        logger = configure_logging(
            log_directory,
            int(logging_config.get("retention_days", 30)),
            logging_config.get("level", "INFO"),
            run_id,
        )
        runner = DailyRunner(settings, database_path, logger, now=parse_now())
        result = runner.run(run_id, args.date, args.force_refresh)
    except (FileNotFoundError, ValueError) as error:
        result = error_payload(run_id, 2, "configuration_error", error, args.date)
    except (sqlite3.Error, OSError) as error:
        result = error_payload(run_id, 5, "storage_failed", error, args.date)
    except Exception as error:
        result = error_payload(run_id, 6, "unexpected_error", error, args.date)

    payload = result.to_dict() if hasattr(result, "to_dict") else result
    if human:
        render_human(payload)
    else:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return int(payload["exit_code"])


def error_payload(run_id: str, exit_code: int, status: str, error: Exception, requested_date):
    now = parse_now() or datetime.now().astimezone()
    target = requested_date or now.date()
    return {
        "schema_version": "2.0",
        "ok": False,
        "status": status,
        "exit_code": exit_code,
        "run_id": run_id,
        "generated_at": now.isoformat(),
        "requested_date": target.isoformat(),
        "expected_trade_date": target.isoformat(),
        "as_of_date": None,
        "is_trading_day": False,
        "is_fresh": False,
        "quality_status": None,
        "result": None,
        "sources": {},
        "storage": {},
        "retry": {"recommended": False, "after_seconds": None},
        "errors": [{"type": type(error).__name__, "message": str(error)}],
    }


def render_human(payload: dict) -> None:
    result = payload.get("result")
    if not result:
        print(f"运行失败: {payload['status']}")
        for error in payload.get("errors", []):
            print(f"- {error.get('message', error)}")
        return
    components = result["components"]
    print("=" * 50)
    print("📊 A股恐慌指数")
    print("=" * 50)
    print(f"日期: {payload['as_of_date']}")
    print(f"恐慌指数: {result['panic_index']:.2f} ({result['status']})")
    print(f"波动率: {components['volatility_percent']:.2f}%")
    print(f"涨跌停比: {components['limit_ratio'] * 100:.1f}%")
    print(f"操作建议: {result['signal']['reason']}")
    if payload.get("quality_status") == "provisional":
        print("数据质量: 临时数据，后续将自动复核")
    print("=" * 50)


def run_legacy(args) -> int:
    if args.command == "history":
        from cli.commands.history import cmd_history

        cmd_history(args)
    elif args.command == "chart":
        from a_share_panic_index.charting import run_chart

        return run_chart(args, now=parse_now())
    elif args.command == "backtest":
        from cli.commands.backtest import cmd_backtest

        cmd_backtest(args)
    elif args.command == "alert":
        from cli.commands.alert import cmd_alert

        cmd_alert(args)
    elif args.command == "config":
        from cli.commands.config import cmd_config

        cmd_config(args)
    elif args.command == "monitor":
        from cli.commands.monitor import cmd_monitor

        cmd_monitor(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_utf8()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliArgumentError as error:
        payload = error_payload(str(uuid4()), 2, "argument_error", error, None)
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 2
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "daily":
        return run_daily(args, human=False)
    if args.command == "current":
        return run_daily(args, human=True)
    return run_legacy(args)


if __name__ == "__main__":
    raise SystemExit(main())
