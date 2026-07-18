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

from a_share_panic_index import APP_VERSION
from a_share_panic_index.calendar import TradingCalendar
from a_share_panic_index.chart import (
    DEFAULT_CHART_PERIOD,
    ChartDataError,
    ChartStaleError,
    generate_chart,
)
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

    for command, help_text in (
        ("daily", "单次生成结构化日报"),
        ("current", "显示当前市场压力指数"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument(
            "--date", type=parse_date, help="指定交易日 YYYY-MM-DD"
        )
        command_parser.add_argument(
            "--force-refresh", action="store_true", help="强制重建历史窗口"
        )
        command_parser.add_argument("--config", help="配置文件路径")
        command_parser.add_argument("--database", help="SQLite数据库路径")

    chart_parser = subparsers.add_parser("chart", help="生成动态模型图表")
    chart_parser.add_argument("--config", help="配置文件路径")
    chart_parser.add_argument("--database", help="SQLite数据库路径")
    chart_parser.add_argument("--output", "-o", default="reports/panic_index.png")
    chart_parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=None,
        help="可选覆盖；默认显示近1年实际交易记录",
    )
    chart_parser.add_argument("--dpi", type=int, default=160)
    return parser


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期格式必须为 YYYY-MM-DD") from error


def parse_now() -> datetime | None:
    value = os.environ.get("PANIC_INDEX_NOW")
    return datetime.fromisoformat(value) if value else None


def previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def resolve_database_path(settings: Settings, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    database_config = settings.section("database")
    return settings.resolve_path(database_config.get("path", "./data_cache/panic_index.db"))


def build_logger(settings: Settings, run_id: str):
    logging_config = settings.section("logging")
    log_directory = settings.resolve_path(logging_config.get("directory", "./logs"))
    return configure_logging(
        log_directory,
        int(logging_config.get("retention_days", 30)),
        logging_config.get("level", "INFO"),
        run_id,
    )


def write_json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_daily(args, human: bool = False) -> int:
    run_id = str(uuid4())
    try:
        settings = Settings(args.config)
        database_path = resolve_database_path(settings, args.database)
        logger = build_logger(settings, run_id)
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
        write_json(payload)
    return int(payload["exit_code"])


def run_chart(args) -> int:
    run_id = str(uuid4())
    now = parse_now() or datetime.now().astimezone()
    generated_at = now.isoformat()
    logger = None
    try:
        settings = Settings(args.config)
        database_path = resolve_database_path(settings, args.database)
        logger = build_logger(settings, run_id)
        output_path = Path(args.output).expanduser().resolve()
        market = settings.section("market")
        calendar = TradingCalendar(
            market.get("calendar", "XSHG"),
            market.get("timezone", "Asia/Shanghai"),
            market.get("data_ready_time", "15:30"),
        )
        context = calendar.context(now=now)
        period_start_date = None
        period_type = "trading_days"
        if args.days is None:
            candidate = previous_year(context.expected_trade_date)
            sessions = calendar.sessions_in_range(candidate, context.expected_trade_date)
            if not sessions:
                raise ValueError("近1年范围内没有可用交易日")
            period_start_date = sessions[0]
            period_type = DEFAULT_CHART_PERIOD
        logger.info(
            "chart开始 database=%s output=%s period=%s days=%s dpi=%s requested=%s expected=%s",
            database_path,
            output_path,
            period_type,
            args.days,
            args.dpi,
            context.requested_date,
            context.expected_trade_date,
        )
        chart = generate_chart(
            database_path,
            output_path,
            days=args.days,
            dpi=args.dpi,
            requested_date=context.requested_date,
            expected_trade_date=context.expected_trade_date,
            market_status=context.status,
            period_start_date=period_start_date,
            period_type=period_type,
        )
        logger.info(
            "chart完成 as_of_date=%s output=%s",
            chart["as_of_date"],
            chart["output"],
        )
        payload = chart_payload(run_id, generated_at, True, "chart_success", 0, chart)
    except (FileNotFoundError, ValueError) as error:
        payload = chart_error_payload(run_id, generated_at, 2, "configuration_error", error)
    except ChartStaleError as error:
        payload = chart_error_payload(run_id, generated_at, 3, "chart_stale", error)
    except ChartDataError as error:
        payload = chart_error_payload(run_id, generated_at, 4, "chart_data_invalid", error)
    except sqlite3.Error as error:
        payload = chart_error_payload(run_id, generated_at, 5, "chart_storage_failed", error)
    except (ImportError, OSError) as error:
        payload = chart_error_payload(run_id, generated_at, 5, "chart_generation_failed", error)
    except Exception as error:
        payload = chart_error_payload(run_id, generated_at, 6, "unexpected_error", error)
    if logger is not None and not payload["ok"]:
        logger.error(
            "chart失败 status=%s error=%s",
            payload["status"],
            payload["errors"][0]["message"],
        )
    write_json(payload)
    return int(payload["exit_code"])


def chart_payload(
    run_id: str,
    generated_at: str,
    ok: bool,
    status: str,
    exit_code: int,
    chart: dict | None,
    errors: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": APP_VERSION,
        "ok": ok,
        "status": status,
        "exit_code": exit_code,
        "run_id": run_id,
        "generated_at": generated_at,
        "chart": chart,
        "retry": {
            "recommended": exit_code == 3,
            "after_seconds": 900 if exit_code == 3 else None,
        },
        "errors": errors or [],
    }


def chart_error_payload(
    run_id: str,
    generated_at: str,
    exit_code: int,
    status: str,
    error: Exception,
) -> dict:
    return chart_payload(
        run_id,
        generated_at,
        False,
        status,
        exit_code,
        None,
        [{"type": type(error).__name__, "message": str(error)}],
    )


def error_payload(
    run_id: str,
    exit_code: int,
    status: str,
    error: Exception,
    requested_date,
):
    now = parse_now() or datetime.now().astimezone()
    target = requested_date or now.date()
    return {
        "schema_version": APP_VERSION,
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
    print("A股市场压力指数")
    print("=" * 50)
    print(f"日期: {payload['as_of_date']}")
    print(f"压力指数: {result['panic_index']:.2f} ({result['status']})")
    print(f"波动率: {components['volatility_percent']:.2f}%")
    print(f"涨跌停比: {components['limit_ratio'] * 100:.1f}%")
    print(f"观察提示: {result['signal']['reason']}")
    if payload.get("quality_status") == "provisional":
        print("数据质量: 临时数据，后续将自动复核")
    print("=" * 50)


def main(argv: list[str] | None = None) -> int:
    configure_utf8()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliArgumentError as error:
        write_json(error_payload(str(uuid4()), 2, "argument_error", error, None))
        return 2
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "daily":
        return run_daily(args, human=False)
    if args.command == "current":
        return run_daily(args, human=True)
    if args.command == "chart":
        return run_chart(args)
    raise AssertionError(f"未处理的命令: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
