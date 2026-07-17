"""恐慌指数滚动分位计算。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .emotion import historical_percentile_series
from .models import REQUIRED_METRICS


class PanicIndexCalculator:
    """仅使用当日之前的数据计算四项指标的历史分位。"""

    def __init__(
        self,
        weights: Mapping[str, float],
        model_config: Mapping[str, Any] | None = None,
    ):
        self.weights = dict(weights)
        model_config = dict(model_config or {})
        self.component_window = int(model_config.get("component_window", 504))
        if self.component_window <= 0:
            raise ValueError("指标滚动分位窗口必须为正整数")

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        missing = [metric for metric in REQUIRED_METRICS if metric not in data.columns]
        if missing:
            raise ValueError(f"缺少必需指标列: {', '.join(missing)}")

        frame = data.copy()
        frame.index = pd.to_datetime(frame.index)
        if frame.index.has_duplicates:
            raise ValueError("指标数据包含重复日期")
        frame.sort_index(inplace=True)
        for metric in REQUIRED_METRICS:
            frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
        frame = frame.dropna(subset=list(REQUIRED_METRICS))
        if frame.empty:
            raise ValueError("没有四项指标均完整的日期")
        metric_values = frame.loc[:, list(REQUIRED_METRICS)].to_numpy(dtype=float)
        if not np.isfinite(metric_values).all():
            raise ValueError("必需指标包含无效数值")

        frame["volatility_score"] = historical_percentile_series(
            frame["volatility"], self.component_window
        )
        frame["limit_score"] = historical_percentile_series(
            frame["limit_ratio"], self.component_window
        )
        frame["basis_score"] = historical_percentile_series(
            frame["futures_basis"], self.component_window
        )
        frame["southbound_score"] = historical_percentile_series(
            -frame["southbound_flow"], self.component_window
        )
        weights = {
            "volatility": float(self.weights.get("volatility", 0.40)),
            "limit_ratio": float(self.weights.get("limit_up_down_ratio", 0.30)),
            "futures_basis": float(self.weights.get("futures_premium", 0.20)),
            "southbound_flow": float(self.weights.get("southbound_flow", 0.10)),
        }
        if any(not np.isfinite(value) or value < 0 for value in weights.values()):
            raise ValueError("指标权重必须是有限的非负数")
        weight_sum = sum(weights.values())
        if weight_sum <= 0:
            raise ValueError("指标权重之和必须大于0")
        frame["panic_index"] = (
            weights["volatility"] * frame["volatility_score"]
            + weights["limit_ratio"] * frame["limit_score"]
            + weights["futures_basis"] * frame["basis_score"]
            + weights["southbound_flow"] * frame["southbound_score"]
        ) * 100 / weight_sum
        return frame
