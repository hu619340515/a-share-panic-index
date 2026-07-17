"""刷新 v4 数据并生成唯一的综合图表。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .charts import Visualizer
from .config import Settings
from .logging_utils import configure_logging
from .pipeline import ChartDataRunner


def run_chart(args, now: datetime | None = None) -> int:
    """生成综合图，并在标准输出写入单个 JSON 对象。"""

    try:
        settings = Settings(getattr(args, "config", None))
        database_config = settings.section("database")
        database_arg = getattr(args, "database", None)
        database_path = (
            Path(database_arg).expanduser().resolve()
            if database_arg
            else settings.resolve_path(
                database_config.get("path", "./data_cache/panic_index.db")
            )
        )
        logging_config = settings.section("logging")
        logger = configure_logging(
            settings.resolve_path(logging_config.get("directory", "./logs")),
            int(logging_config.get("retention_days", 30)),
            logging_config.get("level", "INFO"),
            str(uuid4()),
        )
        runner = ChartDataRunner(settings, database_path, logger, now=now)
        requested_date = getattr(args, "date", None)
        force_refresh = bool(getattr(args, "force_refresh", False))
        refresh_result = runner.run(str(uuid4()), requested_date, force_refresh)

        days = int(getattr(args, "days", 120))
        frame = _load_trading_snapshots(runner.database, runner.calendar, days)
        if len(frame) < days and refresh_result.ok and not force_refresh:
            print(
                f"数据库只有 {len(frame)} 个交易日，正在重建历史窗口以补足 {days} 日",
                file=sys.stderr,
            )
            refresh_result = runner.run(str(uuid4()), requested_date, True)
            frame = _load_trading_snapshots(runner.database, runner.calendar, days)
        if frame.empty:
            exit_code = int(refresh_result.exit_code or 4)
            _emit(
                {
                    "schema_version": "1.0",
                    "ok": False,
                    "status": refresh_result.status,
                    "exit_code": exit_code,
                    "chart_path": None,
                    "requested_trading_days": days,
                    "trading_days": 0,
                    "errors": refresh_result.errors,
                }
            )
            return exit_code

        raw_data = _load_index_series(runner.database.load_observations(), frame.index)
        output_path = (
            Path(getattr(args, "output", "reports/panic_index.png"))
            .expanduser()
            .resolve()
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        visualizer = Visualizer(viz_config=settings.section("viz"))
        visualizer.plot_comprehensive(frame, raw_data, str(output_path))

        latest = frame.iloc[-1]
        payload = {
            "schema_version": "1.0",
            "ok": True,
            "status": "chart_generated",
            "exit_code": 0,
            "chart_path": str(output_path),
            "requested_trading_days": days,
            "trading_days": len(frame),
            "as_of_date": frame.index[-1].strftime("%Y-%m-%d"),
            "panic_index": round(float(latest["panic_index"]), 4),
            "emotion": str(latest.get("status", "未知")),
            "quality_status": str(latest.get("quality_status", "unknown")),
            "is_fresh": bool(refresh_result.is_fresh),
            "refresh_status": refresh_result.status,
            "errors": refresh_result.errors,
        }
        _emit(payload)
        return 0
    except (FileNotFoundError, ValueError) as error:
        return _emit_error(2, "configuration_error", error)
    except Exception as error:
        return _emit_error(5, "chart_failed", error)


def _load_index_series(observations: pd.DataFrame, dates: pd.DatetimeIndex) -> dict:
    if observations.empty:
        return {}
    index_rows = observations[observations["metric"].eq("hs300_close")].copy()
    if index_rows.empty:
        return {}
    index_rows["date"] = pd.to_datetime(index_rows["date"]).dt.normalize()
    series = index_rows.drop_duplicates("date", keep="last").set_index("date")["value"]
    series = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    series = series[series.index.isin(pd.DatetimeIndex(dates).normalize())]
    return {"hs300": series} if not series.empty else {}


def _load_trading_snapshots(database, calendar, days: int) -> pd.DataFrame:
    """读取最近 N 个有效交易日，剔除周末和交易所休市日。"""

    if days <= 0:
        raise ValueError("图表天数必须为正整数")
    candidates = database.load_snapshots(max(days * 2, days + 40))
    if candidates.empty:
        return candidates
    mask = [calendar.is_session(timestamp.date()) for timestamp in candidates.index]
    return candidates.loc[mask].tail(days)


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _emit_error(exit_code: int, status: str, error: Exception) -> int:
    _emit(
        {
            "schema_version": "1.0",
            "ok": False,
            "status": status,
            "exit_code": exit_code,
            "chart_path": None,
            "errors": [{"type": type(error).__name__, "message": str(error)}],
        }
    )
    return exit_code
