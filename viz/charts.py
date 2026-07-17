"""A 股恐慌指数可视化。"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec


class Visualizer:
    """同时兼容 v4 快照和旧版 DataFrame 的图表生成器。"""

    def __init__(self, viz_config: dict[str, Any] | None = None):
        self.viz_config, self.thresholds = self._load_config(viz_config)
        self.dpi = int(self.viz_config.get("dpi", 150))
        self.chinese_font, self.font_path = self._resolve_chinese_font()

        style = self.viz_config.get("style", "seaborn-v0_8-whitegrid")
        try:
            plt.style.use(style)
        except OSError:
            plt.style.use("default")

        plt.rcParams["axes.unicode_minus"] = False
        if self.font_path:
            plt.rcParams["font.family"] = self.chinese_font.get_name()
        else:
            warnings.warn(
                "未找到支持中文的字体；请设置 viz.font_path 或 PANIC_INDEX_FONT_PATH",
                RuntimeWarning,
                stacklevel=2,
            )

    @staticmethod
    def _load_config(viz_config: dict[str, Any] | None):
        if viz_config is not None:
            return dict(viz_config), {
                "greedy": 20,
                "optimistic": 40,
                "neutral": 60,
                "panic": 80,
                "extreme_panic": 100,
            }
        try:
            from config import get_config

            config = get_config()
            return dict(config.viz_config), dict(config.thresholds)
        except Exception:
            return {}, {
                "greedy": 20,
                "optimistic": 40,
                "neutral": 60,
                "panic": 80,
                "extreme_panic": 100,
            }

    def _resolve_chinese_font(self) -> tuple[fm.FontProperties, str | None]:
        configured = os.environ.get("PANIC_INDEX_FONT_PATH") or self.viz_config.get(
            "font_path"
        )
        candidate_paths = [configured] if configured else []
        windir = Path(os.environ.get("WINDIR", "C:/Windows"))
        candidate_paths.extend(
            [
                windir / "Fonts" / "msyh.ttc",
                windir / "Fonts" / "msyhbd.ttc",
                windir / "Fonts" / "simhei.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            ]
        )
        for candidate in candidate_paths:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            if path.is_file():
                fm.fontManager.addfont(str(path))
                return fm.FontProperties(fname=str(path)), str(path.resolve())

        for family in (
            "Microsoft YaHei",
            "Noto Sans CJK SC",
            "Noto Sans CJK JP",
            "SimHei",
            "WenQuanYi Micro Hei",
            "PingFang SC",
            "Arial Unicode MS",
        ):
            try:
                path = fm.findfont(
                    fm.FontProperties(family=family), fallback_to_default=False
                )
            except ValueError:
                continue
            if path and Path(path).is_file():
                return fm.FontProperties(fname=path), str(Path(path).resolve())
        return fm.FontProperties(), None

    def plot_comparison(
        self,
        df: pd.DataFrame,
        raw_data: dict | None,
        output_path: str = "panic_vs_index.png",
    ) -> None:
        frame = self._prepare_frame(df)
        fig, ax = plt.subplots(figsize=(16, 8))
        self._plot_panic_vs_index(ax, frame, raw_data or {})
        ax.set_xlabel("日期", fontproperties=self.chinese_font, fontsize=11)
        self._format_trading_dates(ax, frame.index)
        latest = frame.iloc[-1]
        fig.suptitle(
            self._dashboard_title(latest, frame.index[-1], len(frame)),
            fontproperties=self.chinese_font,
            fontsize=15,
            fontweight="bold",
        )
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        self._save(fig, output_path)

    def plot_comprehensive(
        self,
        df: pd.DataFrame,
        raw_data: dict | None,
        output_path: str = "comprehensive_chart.png",
    ) -> None:
        frame = self._prepare_frame(df)
        figure_size = self.viz_config.get("figure_size", [16, 24])
        fig = plt.figure(figsize=tuple(figure_size))
        gs = GridSpec(5, 1, height_ratios=[2, 1, 1, 1, 1], hspace=0.4)

        axes = [fig.add_subplot(gs[0])]
        axes.extend(fig.add_subplot(gs[index], sharex=axes[0]) for index in range(1, 5))
        self._plot_panic_vs_index(axes[0], frame, raw_data or {})
        self._plot_panic_index(axes[1], frame)
        self._plot_volatility(axes[2], frame)
        self._plot_limit_up_down(axes[3], frame, raw_data or {})
        self._plot_southbound(axes[4], frame)

        for ax in axes:
            ax.tick_params(axis="x", labelbottom=True)
            self._format_trading_dates(ax, frame.index)
        axes[-1].set_xlabel("日期", fontproperties=self.chinese_font, fontsize=11)

        latest = frame.iloc[-1]
        fig.suptitle(
            self._dashboard_title(latest, frame.index[-1], len(frame)),
            fontproperties=self.chinese_font,
            fontsize=15,
            fontweight="bold",
            y=0.995,
        )
        fig.subplots_adjust(top=0.965, bottom=0.04, left=0.08, right=0.92, hspace=0.4)
        self._save(fig, output_path)

    def plot_simple(
        self, df: pd.DataFrame, output_path: str = "panic_index.png"
    ) -> None:
        frame = self._prepare_frame(df)
        fig, ax = plt.subplots(figsize=(12, 6))
        self._plot_panic_index(ax, frame)
        ax.set_xlabel("日期", fontproperties=self.chinese_font, fontsize=11)
        self._format_trading_dates(ax, frame.index)
        fig.tight_layout()
        self._save(fig, output_path)

    def _plot_panic_vs_index(
        self, ax, frame: pd.DataFrame, raw_data: dict[str, Any]
    ) -> None:
        self._draw_emotion_background(ax, frame, alpha=0.13)
        panic_line = ax.plot(
            self._x_values(frame),
            frame["panic_index"],
            linewidth=1.7,
            color="#1565c0",
            label="恐慌指数",
            zorder=4,
        )
        ax.set_ylabel(
            "恐慌指数", fontproperties=self.chinese_font, fontsize=11, color="#1565c0"
        )
        ax.tick_params(axis="y", labelcolor="#1565c0")
        ax.set_ylim(0, 100)
        self._set_trading_xlim(ax, frame)
        ax.set_title(
            "恐慌指数与沪深300对比",
            fontproperties=self.chinese_font,
            fontsize=12,
            fontweight="bold",
        )

        lines = list(panic_line)
        labels = ["恐慌指数"]
        index_series = self._series_from(raw_data, "hs300")
        if index_series is None:
            index_series = self._series(frame, "hs300_close")
        if index_series is not None:
            index_series = index_series.reindex(frame.index)
        if index_series is not None and index_series.notna().any():
            valid = index_series.notna().to_numpy()
            index_axis = ax.twinx()
            index_line = index_axis.plot(
                self._x_values(frame)[valid],
                index_series.to_numpy()[valid],
                linewidth=1.4,
                color="#c62828",
                alpha=0.85,
                label="沪深300",
            )
            index_axis.set_ylabel(
                "沪深300点位", fontproperties=self.chinese_font, fontsize=11
            )
            self._set_trading_xlim(index_axis, frame)
            lines.extend(index_line)
            labels.append("沪深300")
        else:
            ax.text(
                0.99,
                0.03,
                "无沪深300点位数据",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                color="#666666",
                fontproperties=self.chinese_font,
            )
        ax.legend(lines, labels, loc="upper left", prop=self.chinese_font, fontsize=9)
        ax.grid(alpha=0.25)

    def _plot_panic_index(self, ax, frame: pd.DataFrame) -> None:
        self._draw_emotion_background(ax, frame, alpha=0.2)
        ax.plot(
            self._x_values(frame),
            frame["panic_index"],
            linewidth=1.5,
            color="#1565c0",
            label="恐慌指数",
            zorder=4,
        )
        dynamic = self._dynamic_thresholds(frame)
        if dynamic:
            for column, label, color in (
                ("threshold_p05", "P05 极度平静", "#2e7d32"),
                ("threshold_p25", "P25 偏平静", "#7cb342"),
                ("threshold_p75", "P75 偏恐慌", "#ef6c00"),
                ("threshold_p95", "P95 极度恐慌", "#c62828"),
            ):
                ax.plot(
                    self._x_values(frame),
                    frame[column],
                    color=color,
                    linewidth=0.9,
                    linestyle="--",
                    alpha=0.8,
                    label=label,
                )
        ax.set_ylabel("恐慌指数", fontproperties=self.chinese_font, fontsize=11)
        ax.set_title(
            "A股恐慌指数（v4 动态分位）",
            fontproperties=self.chinese_font,
            fontsize=12,
            fontweight="bold",
        )
        ax.set_ylim(0, 100)
        self._set_trading_xlim(ax, frame)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", prop=self.chinese_font, fontsize=8, ncol=3)

        latest = frame.iloc[-1]
        status = str(latest.get("status", "未知"))
        ax.annotate(
            f'{latest["panic_index"]:.1f}\n{status}',
            xy=(len(frame) - 1, latest["panic_index"]),
            xytext=(-8, 12),
            textcoords="offset points",
            ha="right",
            bbox={"boxstyle": "round", "facecolor": "#fff176", "alpha": 0.85},
            fontsize=9,
            fontweight="bold",
            fontproperties=self.chinese_font,
        )

    def _plot_volatility(self, ax, frame: pd.DataFrame) -> None:
        volatility = self._series(frame, "volatility")
        if volatility is None:
            volatility = self._series(frame, "iv")
            if volatility is not None and volatility.abs().max() <= 2:
                volatility = volatility * 100
        elif volatility.abs().max() <= 2:
            volatility = volatility * 100

        ax.set_ylabel("波动率 (%)", fontproperties=self.chinese_font, fontsize=10)
        ax.set_title(
            "沪深300 20日年化波动率",
            fontproperties=self.chinese_font,
            fontsize=12,
        )
        if volatility is None or volatility.dropna().empty:
            self._show_no_data(ax, "无波动率数据")
            return
        values = volatility.astype(float)
        valid = values.notna().to_numpy()
        x_values = self._x_values(frame)[valid]
        y_values = values.to_numpy()[valid]
        ax.plot(x_values, y_values, linewidth=1.4, color="#d32f2f")
        ax.fill_between(x_values, 0, y_values, alpha=0.22, color="#ef5350")
        self._set_trading_xlim(ax, frame)
        ax.grid(alpha=0.25)

    def _plot_limit_up_down(
        self, ax, frame: pd.DataFrame, raw_data: dict[str, Any]
    ) -> None:
        limit_up = self._series(frame, "limit_up")
        if limit_up is None:
            limit_up = self._series_from(raw_data, "limit_up")
        limit_down = self._series(frame, "limit_down")
        if limit_down is None:
            limit_down = self._series_from(raw_data, "limit_down")
        ax.set_ylabel("家数", fontproperties=self.chinese_font, fontsize=10)
        ax.set_title("每日涨跌停家数", fontproperties=self.chinese_font, fontsize=12)
        if limit_up is None or limit_down is None:
            self._show_no_data(ax, "无涨跌停家数数据")
            return
        aligned = pd.concat(
            [limit_up.rename("limit_up"), limit_down.rename("limit_down")], axis=1
        ).reindex(frame.index).dropna()
        if aligned.empty:
            self._show_no_data(ax, "无涨跌停家数数据")
            return
        x_values = frame.index.get_indexer(aligned.index)
        ax.bar(
            x_values,
            aligned["limit_up"],
            alpha=0.72,
            color="#ef5350",
            label="涨停",
            width=0.8,
        )
        ax.bar(
            x_values,
            -aligned["limit_down"],
            alpha=0.72,
            color="#26a69a",
            label="跌停",
            width=0.8,
        )
        ax.axhline(y=0, color="#333333", linewidth=0.6)
        self._set_trading_xlim(ax, frame)
        ax.legend(loc="upper left", prop=self.chinese_font, fontsize=8)
        ax.grid(alpha=0.25, axis="y")

        latest = aligned.iloc[-1]
        ax.text(
            0.99,
            0.96,
            f'涨停: {int(latest["limit_up"])}\n跌停: {int(latest["limit_down"])}',
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontproperties=self.chinese_font,
            fontsize=9,
        )

    def _plot_southbound(self, ax, frame: pd.DataFrame) -> None:
        flow = self._series(frame, "southbound_flow")
        ax.set_ylabel("净流入 (亿港元)", fontproperties=self.chinese_font, fontsize=10)
        ax.set_title("南向资金（港股通）", fontproperties=self.chinese_font, fontsize=12)
        if flow is None or flow.dropna().empty:
            self._show_no_data(ax, "无南向资金数据")
            return
        flow = flow.reindex(frame.index).dropna().astype(float)
        x_values = frame.index.get_indexer(flow.index)
        colors = np.where(flow.to_numpy() >= 0, "#26a69a", "#ef5350")
        ax.bar(x_values, flow, alpha=0.72, color=colors, width=0.8)
        ax.axhline(y=0, color="#333333", linewidth=0.6)
        self._set_trading_xlim(ax, frame)
        ax.grid(alpha=0.25, axis="y")
        ax.text(
            0.02,
            0.95,
            f"区间累计: {flow.sum():.1f}亿",
            transform=ax.transAxes,
            fontsize=9,
            va="top",
            bbox={"boxstyle": "round", "facecolor": "#fff3e0", "alpha": 0.7},
            fontproperties=self.chinese_font,
        )

    def _draw_emotion_background(
        self, ax, frame: pd.DataFrame, alpha: float = 0.15
    ) -> None:
        thresholds = self._dynamic_thresholds(frame)
        x_values = self._x_values(frame)
        if thresholds:
            p05 = frame["threshold_p05"].astype(float).to_numpy()
            p25 = frame["threshold_p25"].astype(float).to_numpy()
            p75 = frame["threshold_p75"].astype(float).to_numpy()
            p95 = frame["threshold_p95"].astype(float).to_numpy()
            bands = (
                (np.zeros(len(frame)), p05, "#81c784"),
                (p05, p25, "#dce775"),
                (p25, p75, "#eeeeee"),
                (p75, p95, "#ffb74d"),
                (p95, np.full(len(frame), 100.0), "#e57373"),
            )
            for lower, upper, color in bands:
                ax.fill_between(x_values, lower, upper, color=color, alpha=alpha)
            return

        values = [
            0,
            float(self.thresholds.get("greedy", 20)),
            float(self.thresholds.get("optimistic", 40)),
            float(self.thresholds.get("neutral", 60)),
            float(self.thresholds.get("panic", 80)),
            100,
        ]
        colors = ["#81c784", "#dce775", "#eeeeee", "#ffb74d", "#e57373"]
        for lower, upper, color in zip(values[:-1], values[1:], colors):
            ax.axhspan(lower, upper, color=color, alpha=alpha)

    @staticmethod
    def _dynamic_thresholds(frame: pd.DataFrame) -> bool:
        columns = {"threshold_p05", "threshold_p25", "threshold_p75", "threshold_p95"}
        return (
            columns.issubset(frame.columns)
            and frame[list(columns)].notna().any().all()
        )

    @staticmethod
    def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("没有可绘制的数据")
        if "panic_index" not in df.columns:
            raise ValueError("绘图数据缺少 panic_index 列")
        frame = df.copy()
        frame.index = pd.to_datetime(frame.index).normalize()
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        frame["panic_index"] = pd.to_numeric(frame["panic_index"], errors="coerce")
        frame = frame.dropna(subset=["panic_index"])
        if frame.empty:
            raise ValueError("panic_index 列没有有效数值")
        return frame

    @staticmethod
    def _series(frame: pd.DataFrame, name: str) -> pd.Series | None:
        if name not in frame.columns:
            return None
        series = pd.to_numeric(frame[name], errors="coerce")
        series.index = pd.to_datetime(series.index).normalize()
        return series

    @staticmethod
    def _series_from(data: dict[str, Any], name: str) -> pd.Series | None:
        value = data.get(name)
        if value is None:
            return None
        if isinstance(value, pd.DataFrame):
            if value.shape[1] != 1:
                return None
            value = value.iloc[:, 0]
        if not isinstance(value, pd.Series):
            return None
        series = pd.to_numeric(value, errors="coerce")
        series.index = pd.to_datetime(series.index).normalize()
        return series.sort_index()

    def _show_no_data(self, ax, message: str) -> None:
        ax.text(
            0.5,
            0.5,
            message,
            transform=ax.transAxes,
            ha="center",
            va="center",
            color="#777777",
            fontsize=11,
            fontproperties=self.chinese_font,
        )
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.15)

    @staticmethod
    def _x_values(frame: pd.DataFrame) -> np.ndarray:
        return np.arange(len(frame), dtype=float)

    @staticmethod
    def _set_trading_xlim(ax, frame: pd.DataFrame) -> None:
        ax.set_xlim(-0.5, len(frame) - 0.5)

    @staticmethod
    def _format_trading_dates(ax, dates: pd.DatetimeIndex) -> None:
        """以连续交易日为横轴，同时显示真实日期标签。"""

        count = len(dates)
        if count == 0:
            return
        tick_count = min(9, count)
        positions = np.unique(np.linspace(0, count - 1, tick_count, dtype=int))
        labels = [pd.Timestamp(dates[position]).strftime("%Y-%m-%d") for position in positions]
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_xlim(-0.5, count - 0.5)

    @staticmethod
    def _dashboard_title(
        latest: pd.Series, latest_date: pd.Timestamp, trading_days: int
    ) -> str:
        status = str(latest.get("status", "未知"))
        quality = str(latest.get("quality_status", ""))
        quality_text = " | 临时数据" if quality == "provisional" else ""
        return (
            f'A股恐慌指数监控面板 | 当前: {latest["panic_index"]:.1f} '
            f"({status}) | 最近{trading_days}个交易日 | "
            f"{latest_date.strftime('%Y-%m-%d')}{quality_text}"
        )

    def _save(self, fig, output_path: str) -> None:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            path,
            dpi=self.dpi,
            bbox_inches="tight",
            facecolor="white",
            pad_inches=0.25,
        )
        plt.close(fig)
