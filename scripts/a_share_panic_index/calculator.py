"""恐慌指数计算。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .models import REQUIRED_METRICS


class PanicIndexCalculator:
    """沿用现有全局最小最大标准化算法。"""

    def __init__(self, weights: dict[str, float], thresholds: dict[str, float]):
        self.weights = weights
        self.thresholds = thresholds

    @staticmethod
    def standardize(series: pd.Series) -> pd.Series:
        valid = pd.to_numeric(series, errors="coerce").dropna()
        if len(valid) < 5 or valid.max() == valid.min():
            return pd.Series(0.5, index=series.index, dtype=float)
        normalized = (series.astype(float) - valid.min()) / (valid.max() - valid.min())
        return normalized.clip(0, 1)

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        missing = [metric for metric in REQUIRED_METRICS if metric not in data.columns]
        if missing:
            raise ValueError(f"缺少必需指标列: {', '.join(missing)}")

        frame = data.copy().dropna(subset=list(REQUIRED_METRICS))
        if frame.empty:
            raise ValueError("没有四项指标均完整的日期")

        frame["volatility_std"] = self.standardize(frame["volatility"])
        frame["limit_std"] = self.standardize(frame["limit_ratio"])
        frame["basis_std"] = self.standardize(frame["futures_basis"])
        frame["southbound_std"] = self.standardize(-frame["southbound_flow"])
        frame["panic_index"] = (
            self.weights.get("volatility", 0.40) * frame["volatility_std"]
            + self.weights.get("limit_up_down_ratio", 0.30) * frame["limit_std"]
            + self.weights.get("futures_premium", 0.20) * frame["basis_std"]
            + self.weights.get("southbound_flow", 0.10) * frame["southbound_std"]
        ) * 100
        frame["status"] = frame["panic_index"].apply(self.get_status)
        return frame

    def get_status(self, value: float) -> str:
        if value < self.thresholds.get("greedy", 20):
            return "贪婪"
        if value < self.thresholds.get("optimistic", 40):
            return "乐观"
        if value < self.thresholds.get("neutral", 60):
            return "中性"
        if value < self.thresholds.get("panic", 80):
            return "恐慌"
        return "极度恐慌"

    @staticmethod
    def get_signal(value: float) -> dict[str, Any]:
        if value >= 80:
            return {"signal": "buy", "strength": "strong", "reason": "极度恐慌，可能是买入时机"}
        if value >= 60:
            return {"signal": "watch", "strength": "medium", "reason": "恐慌情绪，开始关注机会"}
        if value <= 20:
            return {"signal": "sell", "strength": "strong", "reason": "极度贪婪，注意风险"}
        if value <= 40:
            return {"signal": "hold", "strength": "weak", "reason": "乐观情绪，可持有"}
        return {"signal": "hold", "strength": "neutral", "reason": "中性情绪，观望为主"}
