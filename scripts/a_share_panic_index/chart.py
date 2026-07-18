"""动态情绪模型图表生成。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import APP_VERSION
from .database import DB_SCHEMA_VERSION


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


class ChartDataError(RuntimeError):
    """图表数据库不可用或不是当前模型。"""


def generate_chart(
    database_path: Path,
    output_path: Path,
    days: int = 252,
    dpi: int = 160,
) -> dict[str, Any]:
    """从当前动态模型数据库生成PNG图表。"""

    if days <= 0:
        raise ValueError("图表天数必须大于0")
    if not 72 <= dpi <= 600:
        raise ValueError("图表DPI必须位于72到600之间")
    if output_path.suffix.lower() != ".png":
        raise ValueError("图表输出文件必须使用 .png 扩展名")
    frame = load_chart_data(database_path, days)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_chart(frame, output_path, dpi)
    latest = frame.iloc[-1]
    return {
        "output": str(output_path),
        "format": "png",
        "rows": int(len(frame)),
        "days": int(days),
        "as_of_date": pd.Timestamp(latest["date"]).date().isoformat(),
        "model_version": str(latest["model_version"]),
        "panic_index": round(float(latest["panic_index"]), 4),
        "panic_percentile": round(float(latest["panic_percentile"]), 4),
        "emotion_level": str(latest["emotion_level"]),
        "quality_status": str(latest["quality_status"]),
        "file_size": output_path.stat().st_size,
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


def render_chart(frame: pd.DataFrame, output_path: Path, dpi: int) -> None:
    """延迟导入Matplotlib，避免日报命令加载绘图库。"""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.font_manager as font_manager
    import matplotlib.pyplot as plt

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    selected = next((font for font in candidates if font in available_fonts), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [selected]
    plt.rcParams["axes.unicode_minus"] = False

    dates = frame["date"]
    figure, (score_axis, percentile_axis) = plt.subplots(
        2,
        1,
        figsize=(14, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )
    score_axis.plot(
        dates,
        frame["panic_index"],
        color="#1f4e79",
        linewidth=2.0,
        label="市场压力指数",
    )
    threshold_styles = (
        ("threshold_p05", "P05 极度平静", "#2e8b57"),
        ("threshold_p25", "P25 偏平静", "#7aaa45"),
        ("threshold_p75", "P75 偏恐慌", "#e68a00"),
        ("threshold_p95", "P95 极度恐慌", "#c62828"),
    )
    for column, label, color in threshold_styles:
        score_axis.plot(
            dates,
            frame[column],
            color=color,
            linewidth=1.0,
            linestyle="--",
            alpha=0.85,
            label=label,
        )
    provisional = frame["quality_status"].eq("provisional")
    if provisional.any():
        score_axis.scatter(
            dates[provisional],
            frame.loc[provisional, "panic_index"],
            color="#7b1fa2",
            marker="x",
            s=35,
            label="临时数据",
            zorder=5,
        )
    latest = frame.iloc[-1]
    score_axis.scatter(
        [latest["date"]],
        [latest["panic_index"]],
        color="#111111",
        s=40,
        zorder=6,
    )
    score_axis.annotate(
        f"{latest['panic_index']:.2f}  {latest['emotion_level']}",
        xy=(latest["date"], latest["panic_index"]),
        xytext=(8, 10),
        textcoords="offset points",
        fontsize=10,
    )
    score_axis.set_title(f"A股市场压力指数（动态模型 {APP_VERSION}）", fontsize=16)
    score_axis.set_ylabel("压力指数")
    score_axis.grid(alpha=0.2)
    score_axis.legend(loc="upper left", ncol=3, fontsize=9)

    percentile_axis.axhspan(0, 5, color="#2e8b57", alpha=0.16)
    percentile_axis.axhspan(5, 25, color="#8bc34a", alpha=0.12)
    percentile_axis.axhspan(25, 75, color="#9e9e9e", alpha=0.08)
    percentile_axis.axhspan(75, 95, color="#ff9800", alpha=0.12)
    percentile_axis.axhspan(95, 100, color="#c62828", alpha=0.16)
    percentile_axis.plot(
        dates,
        frame["panic_percentile"],
        color="#512da8",
        linewidth=1.8,
        label="历史分位",
    )
    for level in (5, 25, 75, 95):
        percentile_axis.axhline(level, color="#666666", linewidth=0.6, alpha=0.45)
    percentile_axis.set_ylim(0, 100)
    percentile_axis.set_ylabel("历史分位（%）")
    percentile_axis.set_xlabel("交易日")
    percentile_axis.grid(axis="x", alpha=0.15)
    percentile_axis.legend(loc="upper left")

    locator = mdates.AutoDateLocator(minticks=5, maxticks=10)
    percentile_axis.xaxis.set_major_locator(locator)
    percentile_axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    figure.tight_layout()
    figure.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
