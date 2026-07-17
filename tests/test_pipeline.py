"""图表数据管线核心逻辑单元测试。"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.a_share_panic_index.calculator import PanicIndexCalculator
from scripts.a_share_panic_index.calendar import TradingCalendar
from scripts.a_share_panic_index.database import Database, SCHEMA_VERSION
from scripts.a_share_panic_index.providers import (
    ProviderError,
    ProviderExecutor,
    fetch_jrj_limit_ratio,
)
from scripts.a_share_panic_index.pipeline import combine_observations


class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = PanicIndexCalculator(
            {
                "volatility": 0.4,
                "limit_up_down_ratio": 0.3,
                "futures_premium": 0.2,
                "southbound_flow": 0.1,
            },
            {"greedy": 20, "optimistic": 40, "neutral": 60, "panic": 80},
        )

    def test_volatility_uses_decimal_unit(self):
        frame = pd.DataFrame(
            {
                "volatility": [0.20, 0.22, 0.24, 0.26, 0.28],
                "limit_ratio": [0.1, 0.2, 0.3, 0.4, 0.5],
                "futures_basis": [0.01, 0.02, 0.03, 0.04, 0.05],
                "southbound_flow": [100, 80, 60, 40, 20],
            },
            index=pd.date_range("2026-07-10", periods=5, freq="B"),
        )
        result = self.calculator.calculate(frame)
        self.assertAlmostEqual(result.iloc[-1]["volatility"], 0.28)
        self.assertLessEqual(result["panic_index"].max(), 100)

    def test_empty_or_incomplete_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "缺少必需指标"):
            self.calculator.calculate(pd.DataFrame({"volatility": []}))


class TestTradingCalendar(unittest.TestCase):
    def setUp(self):
        self.calendar = TradingCalendar("XSHG", "Asia/Shanghai", "15:30")
        self.timezone = ZoneInfo("Asia/Shanghai")

    def test_before_ready_time_uses_previous_session(self):
        context = self.calendar.context(
            now=datetime(2026, 7, 17, 15, 0, tzinfo=self.timezone)
        )
        self.assertEqual(context.status, "market_not_ready")
        self.assertEqual(context.expected_trade_date.isoformat(), "2026-07-16")

    def test_after_ready_time_requires_current_session(self):
        context = self.calendar.context(
            now=datetime(2026, 7, 17, 15, 31, tzinfo=self.timezone)
        )
        self.assertEqual(context.status, "ready")
        self.assertEqual(context.expected_trade_date.isoformat(), "2026-07-17")

    def test_weekend_is_skipped(self):
        context = self.calendar.context(
            requested_date=datetime(2026, 7, 11).date(),
            now=datetime(2026, 7, 17, 16, 0, tzinfo=self.timezone),
        )
        self.assertEqual(context.status, "skipped_non_trading_day")
        self.assertEqual(context.expected_trade_date.isoformat(), "2026-07-10")

    def test_future_requested_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不能晚于当前日期"):
            self.calendar.context(
                requested_date=datetime(2026, 7, 18).date(),
                now=datetime(2026, 7, 17, 16, 0, tzinfo=self.timezone),
            )


class TestDatabase(unittest.TestCase):
    def test_incompatible_database_is_backed_up_and_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "panic_index.db"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE panic_index(date TEXT PRIMARY KEY)")
                connection.commit()

            database = Database(path)
            self.assertIsNotNone(database.backup_path)
            self.assertTrue(database.backup_path.exists())
            with closing(sqlite3.connect(path)) as connection:
                version = connection.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)

    def test_transaction_rolls_back_raw_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "panic_index.db")
            observations = pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2026-07-17"),
                        "metric": "volatility",
                        "value": 0.3,
                        "source": "fixture",
                        "provisional": False,
                        "fetched_at": pd.Timestamp("2026-07-17T16:00:00"),
                    }
                ]
            )
            panic_rows = pd.DataFrame(
                [
                    {
                        "panic_index": "invalid",
                        "status": "中性",
                        "volatility": 0.3,
                        "limit_ratio": 0.5,
                        "futures_basis": 0.01,
                        "southbound_flow": 10.0,
                        "quality_status": "final",
                        "sources": {},
                    }
                ],
                index=[pd.Timestamp("2026-07-17")],
            )
            with self.assertRaises(ValueError):
                database.persist(observations, panic_rows)
            with closing(sqlite3.connect(database.path)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM raw_metrics").fetchone()[0]
            self.assertEqual(count, 0)


class TestObservationMerge(unittest.TestCase):
    def test_final_data_replaces_provisional_but_not_reverse(self):
        provisional = observation_frame("fallback", True, 0.35)
        final = observation_frame("primary", False, 0.34)
        merged = combine_observations(provisional, final)
        self.assertEqual(merged.iloc[0]["source"], "primary")
        self.assertFalse(bool(merged.iloc[0]["provisional"]))

        merged_reverse = combine_observations(final, provisional)
        self.assertEqual(merged_reverse.iloc[0]["source"], "primary")
        self.assertFalse(bool(merged_reverse.iloc[0]["provisional"]))


class TestProviderTimeout(unittest.TestCase):
    def test_provider_process_is_terminated_after_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "timeout.json"
            fixture.write_text(
                json.dumps(
                    {
                        "providers": {
                            "eastmoney_index_volatility": {
                                "sleep": 2,
                                "records": [
                                    {
                                        "date": "2026-07-17",
                                        "volatility": 0.3,
                                        "hs300_close": 4500,
                                    }
                                ],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            previous = os.environ.get("PANIC_INDEX_FIXTURE_FILE")
            disabled = os.environ.pop("PANIC_INDEX_DISABLE_SUBPROCESS", None)
            os.environ["PANIC_INDEX_FIXTURE_FILE"] = str(fixture)
            try:
                executor = ProviderExecutor(
                    retries=1,
                    retry_delay=0,
                    timeout=0.2,
                    logger=logging.getLogger("timeout-test"),
                    use_subprocess=True,
                )
                with self.assertRaisesRegex(ProviderError, "超过"):
                    executor.run(
                        "eastmoney_index_volatility",
                        datetime(2026, 7, 1).date(),
                        datetime(2026, 7, 17).date(),
                        datetime(2026, 7, 17).date(),
                        {},
                    )
            finally:
                if previous is None:
                    os.environ.pop("PANIC_INDEX_FIXTURE_FILE", None)
                else:
                    os.environ["PANIC_INDEX_FIXTURE_FILE"] = previous
                if disabled is not None:
                    os.environ["PANIC_INDEX_DISABLE_SUBPROCESS"] = disabled


class TestHistoricalProviders(unittest.TestCase):
    def test_jrj_month_history_is_fetched_concurrently(self):
        thread_names = set()
        lock = threading.Lock()

        class Response:
            def __init__(self, year_month):
                self.year_month = year_month

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 20000,
                    "data": {
                        "list": [
                            {
                                "tradeDate": f"{self.year_month}01",
                                "upLimitCount": 80,
                                "downLimitCount": 20,
                            }
                        ]
                    },
                }

        def fake_post(*args, **kwargs):
            with lock:
                thread_names.add(threading.current_thread().name)
            time.sleep(0.005)
            return Response(kwargs["json"]["yearMonth"])

        with patch("requests.post", side_effect=fake_post) as post:
            result = fetch_jrj_limit_ratio(
                datetime(2023, 7, 1).date(),
                datetime(2026, 7, 17).date(),
                datetime(2026, 7, 17).date(),
                {},
            )

        self.assertEqual(post.call_count, 37)
        self.assertEqual(len(result.data), 37)
        self.assertGreater(len(thread_names), 1)


def observation_frame(source: str, provisional: bool, value: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-07-17"),
                "metric": "volatility",
                "value": value,
                "source": source,
                "provisional": provisional,
                "fetched_at": pd.Timestamp("2026-07-17T16:00:00"),
            }
        ]
    )


if __name__ == "__main__":
    unittest.main()
