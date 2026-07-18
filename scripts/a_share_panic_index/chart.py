"""动态情绪模型图表生成。"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from . import APP_VERSION
from .database import DB_SCHEMA_VERSION


CHART_LAYOUT_VERSION = "2-panel-trading-sessions-v1"

REQUIRED_COLUMNS = {
    "date",
    "panic_index",
    "panic_percentile",
    "emotion_level",
    "model_version",
    "threshold_p05",
    "threshold_p25",
    "threshold_p75",
    "threshold_p95",
    "quality_status",
}

CHINESE_FONTS = (
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "SimHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "Arial Unicode MS",
)

TEXT_ZH = {
    "title": f"A股市场压力指数（动态模型 {APP_VERSION}）",
    "score": "市场压力指数",
    "p05": "P05 极度平静",
    "p25": "P25 偏平静",
    "p75": "P75 偏恐慌",
    "p95": "P95 极度恐慌",
    "provisional": "临时数据",
    "score_axis": "压力指数",
    "percentile": "历史分位",
    "percentile_axis": "历史分位（%）",
    "date_axis": "交易日（仅显示实际交易记录）",
}

TEXT_EN = {
    "title": f"A-Share Market Stress Index (Dynamic Model {APP_VERSION})",
    "score": "Market Stress Index",
    "p05": "P05 Extreme Calm",
    "p25": "P25 Calm",
    "p75": "P75 Stressed",
    "p95": "P95 Extreme Stress",
    "provisional": "Provisional Data",
    "score_axis": "Stress Index",
    "percentile": "Historical Percentile",
    "percentile_axis": "Historical Percentile (%)",
    "date_axis": "Trading Sessions Only",
}

EMOTION_LEVELS_EN = {
    "极度平静": "Extreme Calm",
    "偏平静": "Calm",
    "中性": "Neutral",
    "偏恐慌": "Stressed",
    "极度恐慌": "Extreme Stress",
}


class ChartDataError(RuntimeError):
    """图表数据库不可用或不是当前模型。"""


class ChartStaleError(RuntimeError):
    """图表数据库没有更新到预期交易日。"""


def generate_chart(
    database_path: Path,
    output_path: Path,
    days: int = 252,
    dpi: int = 160,
    requested_date: date | None = None,
    expected_trade_date: date | None = None,
    market_status: str | None = None,
) -> dict[str, Any]:
    """从当前动态模型数据库生成PNG图表。"""

    if days <= 0:
        raise ValueError("图表天数必须大于0")
    if not 72 <= dpi <= 600:
        raise ValueError("图表DPI必须位于72到600之间")
    if output_path.suffix.lower() != ".png":
        raise ValueError("图表输出文件必须使用 .png 扩展名")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    frame = load_chart_data(database_path, days)
    latest = frame.iloc[-1]
    latest_date = pd.Timestamp(latest["date"]).date()
    if expected_trade_date and latest_date < expected_trade_date:
        raise ChartStaleError(
            f"图表数据库最新交易日为 {latest_date.isoformat()}，"
            f"预期交易日为 {expected_trade_date.isoformat()}，请先运行 daily"
        )
    if expected_trade_date and latest_date > expected_trade_date:
        raise ChartDataError(
            f"数据库包含晚于预期交易日的数据: {latest_date.isoformat()}"
        )

    temporary_path = output_path.with_name(
        f".{output_path.stem}.{uuid4().hex}.tmp.png"
    )
    try:
        render_chart(
            frame,
            temporary_path,
            dpi,
            requested_date=requested_date,
            market_status=market_status,
        )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "output": str(output_path),
        "format": "png",
        "layout_version": CHART_LAYOUT_VERSION,
        "rows": int(len(frame)),
        "days": int(days),
        "requested_date": requested_date.isoformat() if requested_date else None,
        "expected_trade_date": (
            expected_trade_date.isoformat() if expected_trade_date else None
        ),
        "as_of_date": latest_date.isoformat(),
        "market_status": market_status,
        "is_fresh": expected_trade_date is None or latest_date == expected_trade_date,
        "model_version": str(latest["model_version"]),
        "panic_index": round(float(latest["panic_index"]), 4),
        "panic_percentile": round(float(latest["panic_percentile"]), 4),
        "emotion_level": str(latest["emotion_level"]),
        "quality_status": str(latest["quality_status"]),
        "file_size": output_path.stat().st_size,
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }


def load_chart_data(database_path: Path, days: int) -> pd.DataFrame:
    """只读加载V4动态模型派生结果。"""

    if not database_path.exists() or not database_path.is_file():
        raise ChartDataError(f"数据库不存在，请先运行 daily: {database_path}")
    with closing(sqlite3.connect(database_path)) as connection:
        metadata_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
        ).fetchone()
        schema_version = None
        if metadata_table:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            schema_version = row[0] if row else None
        if schema_version != DB_SCHEMA_VERSION:
            raise ChartDataError(
                "数据库不是当前V4结构，请先运行 daily 完成备份与重建"
            )
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='panic_index'"
        ).fetchone()
        if not table:
            raise ChartDataError("数据库缺少 panic_index 表，请先运行 daily")
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(panic_index)")
        }
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ChartDataError(
                "数据库仍是旧版结构，请先运行 daily 完成升级；缺少字段: "
                + ", ".join(missing)
            )
        frame = pd.read_sql_query(
            """
            SELECT * FROM (
                SELECT date, panic_index, panic_percentile, emotion_level,
                       model_version, threshold_p05, threshold_p25,
                       threshold_p75, threshold_p95, quality_status
                FROM panic_index
                ORDER BY date DESC
                LIMIT ?
            ) ORDER BY date
            """,
            connection,
            params=(days,),
            parse_dates=["date"],
        )
    if frame.empty:
        raise ChartDataError("数据库没有可用于画图的动态模型数据")
    if frame["date"].isna().any():
        raise ChartDataError("数据库图表日期包含空值或无效格式")
    if frame["date"].duplicated().any():
        raise ChartDataError("数据库图表数据包含重复交易日")
    numeric_columns = [
        "panic_index",
        "panic_percentile",
        "threshold_p05",
        "threshold_p25",
        "threshold_p75",
        "threshold_p95",
    ]
    numeric = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ChartDataError("数据库图表字段包含空值或无效数值")
    frame[numeric_columns] = numeric
    versions = set(frame["model_version"].astype(str))
    if versions != {APP_VERSION}:
        raise ChartDataError(
            "数据库包含非当前模型版本，请先运行 daily 重建: "
            + ", ".join(sorted(versions))
        )
    qualities = set(frame["quality_status"].astype(str))
    if not qualities.issubset({"final", "provisional"}):
        raise ChartDataError("数据库包含未知数据质量状态")
    return frame


def render_chart(
    frame: pd.DataFrame,
    output_path: Path,
    dpi: int,
    requested_date: date | None = None,
    market_status: str | None = None,
) -> None:
    """延迟导入Matplotlib，并按交易记录等距绘制横轴。"""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.font_manager as font_manager
    import matplotlib.pyplot as plt

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected_font = next(
        (font for font in CHINESE_FONTS if font in available_fonts),
        "DejaVu Sans",
    )
    use_chinese = selected_font != "DejaVu Sans"
    text = TEXT_ZH if use_chinese else TEXT_EN
    plt.rcParams["font.sans-serif"] = [selected_font]
    plt.rcParams["axes.unicode_minus"] = False

    dates = pd.to_datetime(frame["date"]).reset_index(drop=True)
    positions = np.arange(len(frame), dtype=float)
    figure, (score_axis, percentile_axis) = plt.subplots(
        2,
        1,
        figsize=(14, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )
    score_axis.plot(
        positions,
        frame["panic_index"],
        color="#1f4e79",
        linewidth=2.0,
        label=text["score"],
    )
    threshold_styles = (
        ("threshold_p05", text["p05"], "#2e8b57"),
        ("threshold_p25", text["p25"], "#7aaa45"),
        ("threshold_p75", text["p75"], "#e68a00"),
        ("threshold_p95", text["p95"], "#c62828"),
    )
    for column, label, color in threshold_styles:
        score_axis.plot(
            positions,
            frame[column],
            color=color,
            linewidth=1.0,
            linestyle="--",
            alpha=0.85,
            label=label,
        )
    provisional = frame["quality_status"].eq("provisional").to_numpy()
    if provisional.any():
        score_axis.scatter(
            positions[provisional],
            frame.loc[provisional, "panic_index"],
            color="#7b1fa2",
            marker="x",
            s=35,
            label=text["provisional"],
            zorder=5,
        )
    latest = frame.iloc[-1]
    latest_position = positions[-1]
    latest_level = str(latest["emotion_level"])
    if not use_chinese:
        latest_level = EMOTION_LEVELS_EN.get(latest_level, "Unknown")
    score_axis.scatter(
        [latest_position],
        [latest["panic_index"]],
        color="#111111",
        s=40,
        zorder=6,
    )
    score_axis.annotate(
        f"{latest['panic_index']:.2f}  {latest_level}",
        xy=(latest_position, latest["panic_index"]),
        xytext=(8, 10),
        textcoords="offset points",
        fontsize=10,
    )
    latest_date = dates.iloc[-1].date()
    figure.suptitle(text["title"], fontsize=16, fontweight="bold")
    score_axis.set_title(
        build_date_note(latest_date, requested_date, market_status, use_chinese),
        fontsize=10,
        color="#555555",
    )
    score_axis.set_ylabel(text["score_axis"])
    score_axis.grid(alpha=0.2)
    score_axis.legend(loc="upper left", ncol=3, fontsize=9)

    percentile_axis.axhspan(0, 5, color="#2e8b57", alpha=0.16)
    percentile_axis.axhspan(5, 25, color="#8bc34a", alpha=0.12)
    percentile_axis.axhspan(25, 75, color="#9e9e9e", alpha=0.08)
    percentile_axis.axhspan(75, 95, color="#ff9800", alpha=0.12)
    percentile_axis.axhspan(95, 100, color="#c62828", alpha=0.16)
    percentile_axis.plot(
        positions,
        frame["panic_percentile"],
        color="#512da8",
        linewidth=1.8,
        label=text["percentile"],
    )
    for level in (5, 25, 75, 95):
        percentile_axis.axhline(level, color="#666666", linewidth=0.6, alpha=0.45)
    percentile_axis.set_ylim(0, 100)
    percentile_axis.set_ylabel(text["percentile_axis"])
    percentile_axis.set_xlabel(text["date_axis"])
    percentile_axis.grid(axis="x", alpha=0.15)
    percentile_axis.legend(loc="upper left")

    tick_count = min(8, len(frame))
    tick_positions = np.unique(
        np.linspace(0, len(frame) - 1, num=tick_count).round().astype(int)
    )
    percentile_axis.set_xticks(tick_positions)
    percentile_axis.set_xticklabels(
        [dates.iloc[position].strftime("%Y-%m-%d") for position in tick_positions]
    )
    percentile_axis.set_xlim(-0.5, len(frame) - 0.5)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)


def build_date_note(
    latest_date: date,
    requested_date: date | None,
    market_status: str | None,
    use_chinese: bool,
) -> str:
    if use_chinese:
        if requested_date and market_status == "skipped_non_trading_day":
            return (
                f"运行日 {requested_date.isoformat()} 为非交易日｜"
                f"数据截至最近交易日 {latest_date.isoformat()}"
            )
        if requested_date and market_status == "market_not_ready":
            return (
                f"运行日 {requested_date.isoformat()} 盘后数据尚未就绪｜"
                f"数据截至 {latest_date.isoformat()}"
            )
        return f"数据截至交易日 {latest_date.isoformat()}"

    if requested_date and market_status == "skipped_non_trading_day":
        return (
            f"Run date {requested_date.isoformat()} is not a trading day | "
            f"Data through {latest_date.isoformat()}"
        )
    if requested_date and market_status == "market_not_ready":
        return (
            f"Run date {requested_date.isoformat()} is not ready | "
            f"Data through {latest_date.isoformat()}"
        )
    return f"Data through trading session {latest_date.isoformat()}"
