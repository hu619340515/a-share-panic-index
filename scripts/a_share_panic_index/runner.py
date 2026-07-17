"""daily 单次运行编排。"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from .calculator import PanicIndexCalculator
from .calendar import TradingCalendar
from .config import Settings
from .database import Database
from .models import REQUIRED_METRICS, ProviderResult, RunResult
from .providers import PROVIDER_CHAINS, ProviderError, ProviderExecutor


class DailyRunner:
    def __init__(
        self,
        settings: Settings,
        database_path,
        logger,
        now: datetime | None = None,
        executor: ProviderExecutor | None = None,
    ):
        self.settings = settings
        self.database = Database(database_path)
        self.logger = logger
        self.now = now

        market = settings.section("market")
        self.calendar = TradingCalendar(
            market.get("calendar", "XSHG"),
            market.get("timezone", "Asia/Shanghai"),
            market.get("data_ready_time", "15:30"),
        )
        network = settings.section("network")
        self.total_timeout = float(network.get("total_timeout", 300))
        self.provider_timeout = float(network.get("provider_timeout", 30))
        self.executor = executor or ProviderExecutor(
            retries=int(network.get("max_retries", 3)),
            retry_delay=float(network.get("retry_delay", 2)),
            timeout=self.provider_timeout,
            logger=logger,
        )

    def run(
        self,
        run_id: str,
        requested_date: date | None = None,
        force_refresh: bool = False,
    ) -> RunResult:
        started = time.monotonic()
        context = self.calendar.context(requested_date=requested_date, now=self.now)
        snapshot = self.database.latest_snapshot()

        if context.status in {"skipped_non_trading_day", "market_not_ready"} and snapshot:
            return self._snapshot_result(run_id, context, snapshot)

        database_config = self.settings.section("database")
        latest = None if force_refresh else self.database.latest_observation_date()
        if latest is None:
            start = context.expected_trade_date - timedelta(
                days=int(database_config.get("rebuild_days", 730))
            )
        else:
            start = latest.date() - timedelta(days=int(database_config.get("overlap_days", 40)))
        end = context.expected_trade_date
        self.logger.info("daily开始 start=%s end=%s force_refresh=%s", start, end, force_refresh)

        observations, provider_errors = self._fetch_all(start, end, end, started)
        existing = self.database.load_observations()
        combined = combine_observations(existing, observations)
        target_rows = combined[pd.to_datetime(combined["date"]).dt.date.eq(end)]
        target_metrics = set(target_rows["metric"])
        missing = [metric for metric in REQUIRED_METRICS if metric not in target_metrics]

        if missing:
            exit_code = 3 if not target_metrics.intersection(REQUIRED_METRICS) else 4
            status = "stale" if exit_code == 3 else "incomplete_data"
            return self._failure_result(
                run_id,
                context,
                status,
                exit_code,
                snapshot,
                provider_errors,
                missing,
            )

        try:
            panic_rows = self._calculate_rows(combined)
        except Exception as error:
            self.logger.exception("指数计算失败")
            return self._exception_result(run_id, context, 5, "calculation_failed", error)

        target_timestamp = pd.Timestamp(end)
        if target_timestamp not in panic_rows.index:
            return self._failure_result(
                run_id,
                context,
                "incomplete_data",
                4,
                snapshot,
                provider_errors,
                list(REQUIRED_METRICS),
            )

        try:
            storage = self.database.persist(observations, panic_rows)
        except Exception as error:
            self.logger.exception("数据库事务失败")
            return self._exception_result(run_id, context, 5, "storage_failed", error)

        target = panic_rows.loc[target_timestamp]
        quality_status = str(target["quality_status"])
        status = context.status if context.status != "ready" else (
            "success_provisional" if quality_status == "provisional" else "success"
        )
        sources = target["sources"]
        storage.update(
            {
                "database": str(self.database.path),
                "backup": str(self.database.backup_path) if self.database.backup_path else None,
                "incremental_start": start.isoformat(),
            }
        )
        return RunResult(
            ok=True,
            status=status,
            exit_code=0,
            run_id=run_id,
            generated_at=self._generated_at(),
            requested_date=context.requested_date,
            expected_trade_date=context.expected_trade_date,
            as_of_date=end,
            is_trading_day=context.is_trading_day,
            is_fresh=True,
            quality_status=quality_status,
            result=self._result_payload(target),
            sources=sources,
            storage=storage,
            retry={"recommended": False, "after_seconds": None},
            errors=provider_errors,
        )

    def _fetch_all(
        self,
        start: date,
        end: date,
        target: date,
        started: float,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        records: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}
        errors: list[dict[str, Any]] = []
        context: dict[str, Any] = {}

        self._fetch_chain(
            PROVIDER_CHAINS["index"],
            ("volatility", "hs300_close"),
            start,
            end,
            target,
            context,
            records,
            errors,
            started,
        )
        context["spot_records"] = [
            {"date": key[0].isoformat(), "hs300_close": record["value"]}
            for key, record in records.items()
            if key[1] == "hs300_close"
        ]
        self._fetch_chain(
            PROVIDER_CHAINS["limit"],
            ("limit_ratio",),
            start,
            end,
            target,
            context,
            records,
            errors,
            started,
        )
        self._fetch_chain(
            PROVIDER_CHAINS["futures"],
            ("futures_basis",),
            start,
            end,
            target,
            context,
            records,
            errors,
            started,
        )
        self._fetch_chain(
            PROVIDER_CHAINS["southbound"],
            ("southbound_flow",),
            start,
            end,
            target,
            context,
            records,
            errors,
            started,
        )

        if not records:
            return empty_observations(), errors
        return pd.DataFrame(records.values()), errors

    def _fetch_chain(
        self,
        providers: list[str],
        target_columns: tuple[str, ...],
        start: date,
        end: date,
        target: date,
        context: dict[str, Any],
        records: dict[tuple[pd.Timestamp, str], dict[str, Any]],
        errors: list[dict[str, Any]],
        started: float,
    ) -> None:
        for provider in providers:
            remaining = self.total_timeout - (time.monotonic() - started)
            if remaining <= 0:
                errors.append({"provider": provider, "type": "timeout", "message": "daily总超时"})
                return
            self.executor.timeout = min(self.provider_timeout, remaining)
            try:
                result = self.executor.run(
                    provider,
                    start,
                    end,
                    target,
                    context,
                    deadline=started + self.total_timeout,
                )
                merge_provider_records(records, result)
                if "hs300_close" in result.data.columns:
                    context["spot_records"] = [
                        {"date": key[0].isoformat(), "hs300_close": record["value"]}
                        for key, record in records.items()
                        if key[1] == "hs300_close"
                    ]
            except ProviderError as error:
                errors.append(
                    {"provider": provider, "type": "provider_error", "message": str(error)}
                )
            if all((pd.Timestamp(target), column) in records for column in target_columns):
                return

    def _calculate_rows(self, observations: pd.DataFrame) -> pd.DataFrame:
        values = observations.pivot(index="date", columns="metric", values="value").sort_index()
        calculator = PanicIndexCalculator(self.settings.weights, self.settings.thresholds)
        calculated = calculator.calculate(values)

        metadata = observations.set_index(["date", "metric"])[
            ["source", "provisional"]
        ].to_dict("index")
        sources = []
        quality = []
        for index in calculated.index:
            date_sources = {}
            provisional = False
            for metric in REQUIRED_METRICS:
                item = metadata[(pd.Timestamp(index), metric)]
                date_sources[metric] = {
                    "provider": item["source"],
                    "provisional": bool(item["provisional"]),
                }
                provisional = provisional or bool(item["provisional"])
            sources.append(date_sources)
            quality.append("provisional" if provisional else "final")
        calculated["sources"] = sources
        calculated["quality_status"] = quality
        return calculated

    def _snapshot_result(self, run_id: str, context, snapshot: dict) -> RunResult:
        as_of = date.fromisoformat(snapshot["date"])
        return RunResult(
            ok=True,
            status=context.status,
            exit_code=0,
            run_id=run_id,
            generated_at=self._generated_at(),
            requested_date=context.requested_date,
            expected_trade_date=context.expected_trade_date,
            as_of_date=as_of,
            is_trading_day=context.is_trading_day,
            is_fresh=as_of == context.expected_trade_date,
            quality_status=snapshot["quality_status"],
            result=self._result_payload(snapshot),
            sources=snapshot["sources"],
            storage={"database": str(self.database.path), "cache_hit": True},
            retry={"recommended": False, "after_seconds": None},
            errors=[],
        )

    def _failure_result(
        self,
        run_id: str,
        context,
        status: str,
        exit_code: int,
        snapshot: dict | None,
        errors: list[dict[str, Any]],
        missing: list[str],
    ) -> RunResult:
        errors = list(errors) + [
            {"type": "missing_metrics", "message": "缺少必需指标", "metrics": missing}
        ]
        as_of = date.fromisoformat(snapshot["date"]) if snapshot else None
        return RunResult(
            ok=False,
            status=status,
            exit_code=exit_code,
            run_id=run_id,
            generated_at=self._generated_at(),
            requested_date=context.requested_date,
            expected_trade_date=context.expected_trade_date,
            as_of_date=as_of,
            is_trading_day=context.is_trading_day,
            is_fresh=False,
            quality_status=snapshot.get("quality_status") if snapshot else None,
            result=self._result_payload(snapshot) if snapshot else None,
            sources=snapshot.get("sources", {}) if snapshot else {},
            storage={"database": str(self.database.path)},
            retry={"recommended": True, "after_seconds": 900},
            errors=errors,
        )

    def _exception_result(self, run_id: str, context, exit_code: int, status: str, error: Exception) -> RunResult:
        return RunResult(
            ok=False,
            status=status,
            exit_code=exit_code,
            run_id=run_id,
            generated_at=self._generated_at(),
            requested_date=context.requested_date,
            expected_trade_date=context.expected_trade_date,
            as_of_date=None,
            is_trading_day=context.is_trading_day,
            is_fresh=False,
            quality_status=None,
            result=None,
            sources={},
            storage={"database": str(self.database.path)},
            retry={"recommended": False, "after_seconds": None},
            errors=[{"type": type(error).__name__, "message": str(error)}],
        )

    def _generated_at(self) -> datetime:
        return self.now or self.calendar.now()

    @staticmethod
    def _result_payload(row) -> dict[str, Any]:
        value = float(row["panic_index"])
        return {
            "panic_index": round(value, 4),
            "status": row["status"],
            "signal": PanicIndexCalculator.get_signal(value),
            "components": {
                "volatility": float(row["volatility"]),
                "volatility_percent": float(row["volatility"]) * 100,
                "limit_ratio": float(row["limit_ratio"]),
                "limit_up": nullable_number(row.get("limit_up")),
                "limit_down": nullable_number(row.get("limit_down")),
                "futures_basis": float(row["futures_basis"]),
                "southbound_flow": float(row["southbound_flow"]),
            },
        }


def empty_observations() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["date", "metric", "value", "source", "provisional", "fetched_at"]
    )


def merge_provider_records(
    records: dict[tuple[pd.Timestamp, str], dict[str, Any]],
    result: ProviderResult,
) -> None:
    for index, row in result.data.iterrows():
        for metric, value in row.items():
            if pd.isna(value):
                continue
            key = (pd.Timestamp(index).normalize(), metric)
            if key in records:
                continue
            records[key] = {
                "date": key[0],
                "metric": metric,
                "value": float(value),
                "source": result.provider,
                "provisional": bool(result.provisional),
                "fetched_at": result.fetched_at,
            }


def combine_observations(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.copy()
    if new.empty:
        return existing.copy()
    combined: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}
    for frame, is_new in ((existing, False), (new, True)):
        for row in frame.to_dict("records"):
            row["date"] = pd.Timestamp(row["date"]).normalize()
            key = (row["date"], row["metric"])
            current = combined.get(key)
            if current is None:
                combined[key] = row
                continue
            if is_new and (not bool(row["provisional"]) or bool(current["provisional"])):
                combined[key] = row
    return pd.DataFrame(combined.values()).sort_values(["date", "metric"]).reset_index(drop=True)


def nullable_number(value):
    if value is None or pd.isna(value):
        return None
    return int(value) if float(value).is_integer() else float(value)


def new_run_id() -> str:
    return str(uuid.uuid4())
