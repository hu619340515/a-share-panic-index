"""动态情绪阈值、趋势和事件计算。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from . import APP_VERSION


DEFAULT_QUANTILES = {
    "extreme_calm": 0.05,
    "calm": 0.25,
    "panic": 0.75,
    "extreme_panic": 0.95,
}

LEVEL_EXTREME_CALM = "极度平静"
LEVEL_CALM = "偏平静"
LEVEL_NEUTRAL = "中性"
LEVEL_PANIC = "偏恐慌"
LEVEL_EXTREME_PANIC = "极度恐慌"


def empirical_percentile(value: float, history: pd.Series) -> float:
    """计算当前值在既有历史中的经验分位，不产生精确的0或1。"""

    numeric = pd.to_numeric(history, errors="coerce").dropna()
    numeric = numeric[np.isfinite(numeric)]
    if numeric.empty:
        return 0.5
    less = int((numeric < value).sum())
    equal = int((numeric == value).sum())
    return float((less + 0.5 * equal + 0.5) / (len(numeric) + 1))


def historical_percentile_series(series: pd.Series, window: int) -> pd.Series:
    """逐日使用此前最多 ``window`` 条记录计算经验分位。"""

    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    result = pd.Series(index=numeric.index, dtype=float)
    for position, (index, value) in enumerate(numeric.items()):
        if pd.isna(value) or not np.isfinite(value):
            result.loc[index] = np.nan
            continue
        start = max(0, position - window)
        history = numeric.iloc[start:position]
        result.loc[index] = empirical_percentile(float(value), history)
    return result


class DynamicEmotionClassifier:
    """使用历史分数生成动态阈值、情绪等级和趋势事件。"""

    def __init__(self, config: Mapping[str, Any] | None = None):
        config = dict(config or {})
        self.model_version = APP_VERSION
        self.min_periods = int(config.get("min_periods", 252))
        self.short_window = int(config.get("short_threshold_window", 252))
        self.long_window = int(config.get("long_threshold_window", 756))
        self.short_weight = float(config.get("short_weight", 0.30))
        self.long_weight = float(config.get("long_weight", 0.70))
        self.smoothing_span = int(config.get("smoothing_span", 20))
        self.quantiles = dict(DEFAULT_QUANTILES)
        configured_quantiles = config.get("quantiles", {})
        unknown_quantiles = set(configured_quantiles) - set(DEFAULT_QUANTILES)
        if unknown_quantiles:
            raise ValueError(
                "未知动态情绪分位配置: "
                + ", ".join(sorted(unknown_quantiles))
            )
        self.quantiles.update(configured_quantiles)
        trend = config.get("trend", {})
        self.fast_change = float(trend.get("fast_change_threshold", 10))
        self.slow_change = float(trend.get("slow_change_threshold", 3))
        self._validate()

    def _validate(self) -> None:
        if min(self.min_periods, self.short_window, self.long_window) <= 0:
            raise ValueError("动态情绪窗口必须为正整数")
        if self.short_window > self.long_window:
            raise ValueError("短期阈值窗口不能大于长期阈值窗口")
        if self.smoothing_span <= 0:
            raise ValueError("阈值平滑周期必须为正整数")
        weight_sum = self.short_weight + self.long_weight
        if weight_sum <= 0:
            raise ValueError("动态阈值权重之和必须大于0")
        self.short_weight /= weight_sum
        self.long_weight /= weight_sum
        ordered = [
            float(self.quantiles["extreme_calm"]),
            float(self.quantiles["calm"]),
            float(self.quantiles["panic"]),
            float(self.quantiles["extreme_panic"]),
        ]
        if ordered != sorted(ordered) or len(set(ordered)) != 4:
            raise ValueError("动态情绪分位阈值必须严格递增")
        if ordered[0] <= 0 or ordered[-1] >= 1:
            raise ValueError("动态情绪分位阈值必须位于0和1之间")

    def classify(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "panic_index" not in frame.columns:
            raise ValueError("缺少 panic_index，无法计算动态情绪阈值")
        result = frame.copy().sort_index()
        scores = pd.to_numeric(result["panic_index"], errors="coerce").astype(float)
        if scores.isna().any() or not np.isfinite(scores).all():
            raise ValueError("panic_index 包含无效数值")

        raw_thresholds: list[dict[str, float]] = []
        percentiles: list[float] = []
        classification_quality: list[str] = []
        for position, score in enumerate(scores):
            history = scores.iloc[:position].dropna()
            short_history = history.tail(self.short_window)
            long_history = history.tail(self.long_window)
            thresholds = {}
            for name, quantile in self.quantiles.items():
                if history.empty:
                    short_value = float(quantile) * 100
                    long_value = float(quantile) * 100
                else:
                    short_value = float(short_history.quantile(float(quantile)))
                    long_value = float(long_history.quantile(float(quantile)))
                thresholds[name] = (
                    self.short_weight * short_value
                    + self.long_weight * long_value
                )
            raw_thresholds.append(thresholds)
            percentiles.append(
                empirical_percentile(float(score), long_history) * 100
            )
            classification_quality.append(
                "final" if len(history) >= self.min_periods else "warming_up"
            )

        raw_frame = pd.DataFrame(raw_thresholds, index=result.index)
        smoothed = raw_frame.ewm(
            span=self.smoothing_span,
            adjust=False,
            min_periods=1,
        ).mean()
        for name in self.quantiles:
            result[f"threshold_{self._threshold_suffix(name)}"] = smoothed[name]

        result["model_version"] = self.model_version
        result["panic_percentile"] = percentiles
        result["classification_quality"] = classification_quality
        result["status"] = [
            self.classify_level(
                float(score),
                {
                    "p05": float(result.iloc[position]["threshold_p05"]),
                    "p25": float(result.iloc[position]["threshold_p25"]),
                    "p75": float(result.iloc[position]["threshold_p75"]),
                    "p95": float(result.iloc[position]["threshold_p95"]),
                },
            )
            for position, score in enumerate(scores)
        ]
        result["previous_level"] = result["status"].shift(1)
        result["level_changed"] = (
            result["previous_level"].notna()
            & result["status"].ne(result["previous_level"])
        )
        result["change_1d"] = scores.diff(1)
        result["change_5d"] = scores.diff(5)
        percentile_series = pd.Series(percentiles, index=result.index, dtype=float)
        result["percentile_change_1d"] = percentile_series.diff(1)
        result["percentile_change_5d"] = percentile_series.diff(5)
        result["trend"] = [
            self.trend_label(change_1d, change_5d)
            for change_1d, change_5d in zip(
                result["change_1d"], result["change_5d"], strict=True
            )
        ]
        result["event"] = [
            self.transition_event(previous, current, trend)
            for previous, current, trend in zip(
                result["previous_level"],
                result["status"],
                result["trend"],
                strict=True,
            )
        ]
        return result

    @staticmethod
    def _threshold_suffix(name: str) -> str:
        return {
            "extreme_calm": "p05",
            "calm": "p25",
            "panic": "p75",
            "extreme_panic": "p95",
        }[name]

    @staticmethod
    def classify_level(score: float, thresholds: Mapping[str, float]) -> str:
        if score < float(thresholds["p05"]):
            return LEVEL_EXTREME_CALM
        if score < float(thresholds["p25"]):
            return LEVEL_CALM
        if score < float(thresholds["p75"]):
            return LEVEL_NEUTRAL
        if score < float(thresholds["p95"]):
            return LEVEL_PANIC
        return LEVEL_EXTREME_PANIC

    def trend_label(self, change_1d: float, change_5d: float) -> str:
        change = change_5d if pd.notna(change_5d) else change_1d
        if pd.isna(change):
            return "基本稳定"
        if change >= self.fast_change:
            return "快速升温"
        if change >= self.slow_change:
            return "缓慢升温"
        if change <= -self.fast_change:
            return "快速缓解"
        if change <= -self.slow_change:
            return "缓慢缓解"
        return "基本稳定"

    @staticmethod
    def transition_event(
        previous: Any,
        current: str,
        trend: str | None = None,
    ) -> str:
        if previous is None or pd.isna(previous):
            return "none"
        if previous == current:
            if trend == "快速升温":
                return "rapidly_heating"
            if trend == "快速缓解":
                return "rapidly_cooling"
            return "none"
        if current == LEVEL_EXTREME_PANIC:
            return "entered_extreme_panic"
        if previous == LEVEL_EXTREME_PANIC:
            return "exited_extreme_panic"
        if current == LEVEL_PANIC:
            return "entered_panic"
        if current == LEVEL_NEUTRAL and previous in {
            LEVEL_PANIC,
            LEVEL_EXTREME_PANIC,
        }:
            return "returned_to_neutral"
        if current == LEVEL_EXTREME_CALM:
            return "entered_extreme_calm"
        if previous == LEVEL_EXTREME_CALM:
            return "exited_extreme_calm"
        return "level_changed"
