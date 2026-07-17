"""真实数据源集成测试，默认不访问公网。"""

from __future__ import annotations

import os
import unittest
from datetime import date


@unittest.skipUnless(
    os.environ.get("RUN_LIVE_TESTS") == "1",
    "真实数据源测试仅在 RUN_LIVE_TESTS=1 时运行",
)
class TestLiveProviders(unittest.TestCase):
    def test_tencent_realtime_fills_current_session_from_sina_history(self):
        from scripts.a_share_panic_index.providers import execute_provider

        start = date(2026, 6, 1)
        end = date(2026, 7, 17)
        history = execute_provider(
            "sina_index_volatility",
            start,
            end,
            end,
            {},
        )
        context = {
            "spot_records": [
                {"date": index.isoformat(), "hs300_close": row["hs300_close"]}
                for index, row in history.data.iterrows()
            ]
        }
        result = execute_provider(
            "tencent_index_realtime",
            start,
            end,
            end,
            context,
        )
        self.assertFalse(result.data.empty)
        self.assertIn("volatility", result.data.columns)
        self.assertIn("hs300_close", result.data.columns)
        self.assertIn(date(2026, 7, 17), result.data.index.date)


if __name__ == "__main__":
    unittest.main()
