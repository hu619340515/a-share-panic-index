"""基于 v4 数据库快照生成图表。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from viz.charts import Visualizer

from .config import Settings
from .logging_utils import configure_logging
from .runner import DailyRunner


def run_chart(args, now: datetime | None = None) -> int:
    """刷新 v4 数据并从同一数据库生成图表。"""

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
        runner = DailyRunner(settings, database_path, logger, now=now)
        requested_date = getattr(args, "date", None)
        force_refresh = bool(getattr(args, "force_refresh", False))
        refresh_result = runner.run(
            str(uuid4()),
            requested_date,
            force_refresh,
        )

        days = int(getattr(args, "days", 120))
        frame = _load_trading_snapshots(runner.database, runner.calendar, days)
        if len(frame) < days and refresh_result.ok and not force_refresh:
            print(
                f"⚠️ 数据库只有 {len(frame)} 个交易日，正在重建历史窗口以补足 {days} 日",
                file=sys.stderr,
            )
            refresh_result = runner.run(str(uuid4()), requested_date, True)
            frame = _load_trading_snapshots(runner.database, runner.calendar, days)
        if frame.empty:
            _print_refresh_errors(refresh_result)
            print("没有可用于绘图的 v4 指数快照", file=sys.stderr)
            return int(refresh_result.exit_code or 4)

        raw_data = _load_index_series(runner.database.load_observations(), frame.index)
        output_path = (
            Path(getattr(args, "output", "panic_chart.png")).expanduser().resolve()
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        visualizer = Visualizer(viz_config=settings.section("viz"))
        chart_type = getattr(args, "type", "comprehensive")
        if chart_type == "simple":
            visualizer.plot_simple(frame, str(output_path))
        elif chart_type == "comparison":
            visualizer.plot_comparison(frame, raw_data, str(output_path))
        else:
            visualizer.plot_comprehensive(frame, raw_data, str(output_path))

        if not refresh_result.ok:
            _print_refresh_errors(refresh_result)
            print(
                f"⚠️ 刷新状态为 {refresh_result.status}，图表使用数据库中的最近有效快照",
                file=sys.stderr,
            )
        print(f"✅ 图表已保存: {output_path}")
        print(
            f"数据模型: v4 | 交易日: {len(frame)}/{days} | "
            f"截止日期: {frame.index[-1].strftime('%Y-%m-%d')}"
        )
        return 0 if refresh_result.result is not None else int(refresh_result.exit_code)
    except (FileNotFoundError, ValueError) as error:
        print(f"图表配置错误: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"图表生成失败: {type(error).__name__}: {error}", file=sys.stderr)
        return 5


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
    """读取最近 N 个有效交易日，剔除误入库的周末和休市日。"""

    if days <= 0:
        raise ValueError("图表天数必须为正整数")
    candidates = database.load_snapshots(max(days * 2, days + 40))
    if candidates.empty:
        return candidates
    mask = [calendar.is_session(timestamp.date()) for timestamp in candidates.index]
    return candidates.loc[mask].tail(days)


def _print_refresh_errors(result) -> None:
    for error in result.errors:
        message = (
            error.get("message", str(error))
            if isinstance(error, dict)
            else str(error)
        )
        print(f"- {message}", file=sys.stderr)
