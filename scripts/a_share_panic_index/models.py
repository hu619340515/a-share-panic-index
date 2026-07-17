"""运行时数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd


REQUIRED_METRICS = (
    "volatility",
    "limit_ratio",
    "futures_basis",
    "southbound_flow",
)


@dataclass
class ProviderResult:
    """单个数据源的标准化结果。"""

    provider: str
    data: pd.DataFrame
    provisional: bool = False
    fetched_at: datetime = field(default_factory=datetime.now)


@dataclass
class MarketContext:
    """交易日和数据新鲜度上下文。"""

    requested_date: date
    expected_trade_date: date
    is_trading_day: bool
    market_ready: bool
    status: str


@dataclass
class RunResult:
    """图表数据刷新结果。"""

    ok: bool
    status: str
    exit_code: int
    run_id: str
    generated_at: datetime
    requested_date: date
    expected_trade_date: date
    as_of_date: date | None
    is_trading_day: bool
    is_fresh: bool
    quality_status: str | None
    result: dict[str, Any] | None
    sources: dict[str, Any]
    storage: dict[str, Any]
    retry: dict[str, Any]
    errors: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.0",
            "ok": self.ok,
            "status": self.status,
            "exit_code": self.exit_code,
            "run_id": self.run_id,
            "generated_at": self.generated_at.isoformat(),
            "requested_date": self.requested_date.isoformat(),
            "expected_trade_date": self.expected_trade_date.isoformat(),
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "is_trading_day": self.is_trading_day,
            "is_fresh": self.is_fresh,
            "quality_status": self.quality_status,
            "result": self.result,
            "sources": self.sources,
            "storage": self.storage,
            "retry": self.retry,
            "errors": self.errors,
        }
