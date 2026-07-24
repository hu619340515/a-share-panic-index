from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.a_share_panic_index.pipeline.daily import DailyPipeline
from scripts.a_share_panic_index.pipeline.realtime import RealtimePipeline
from scripts.a_share_panic_index.validation import run_validation
from scripts.a_share_panic_index.web import create_app
from tests.helpers import REALTIME_FIXTURE, make_database, now, settings, test_logger


class TestWebAndValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = make_database(self.root)
        self.settings = settings()
        self.logger = test_logger()
        realtime = RealtimePipeline(self.settings, self.database, self.logger)
        realtime.run(now(10, 0), fixture=str(REALTIME_FIXTURE))
        realtime.run(now(10, 5), fixture=str(REALTIME_FIXTURE))
        realtime.run(now(15, 10), fixture=str(REALTIME_FIXTURE))
        DailyPipeline(self.settings, self.database, self.logger).run(
            now(16, 0), requested_date=now(16, 0).date()
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_api_contract_and_dashboard(self):
        app = create_app(
            self.settings, self.database, self.logger, start_collector=False
        )
        with TestClient(app) as client:
            realtime = client.get("/api/v1/realtime")
            self.assertEqual(realtime.status_code, 200)
            payload = realtime.json()
            self.assertIn("realtime_panic_index_raw", payload)
            self.assertIn("confidence", payload)
            self.assertIn("reference_mode", payload)
            self.assertEqual(payload["aggregate"]["up_count"], 850)
            self.assertEqual(payload["aggregate"]["bucket_5m"], 48)
            self.assertEqual(client.get("/api/v1/realtime/history").status_code, 200)
            self.assertEqual(client.get("/api/v1/daily/latest").status_code, 200)
            self.assertEqual(client.get("/api/v1/daily/history").status_code, 200)
            self.assertEqual(client.get("/api/v1/sources").status_code, 200)
            self.assertEqual(client.get("/api/v1/reference").status_code, 200)
            health = client.get("/healthz").json()
            self.assertEqual(health["database_journal_mode"], "wal")
            dashboard = client.get("/")
            self.assertIn("盘中实时估计，不是收盘正式值", dashboard.text)

    def test_collector_is_singleton(self):
        app = create_app(
            self.settings,
            self.database,
            self.logger,
            fixture=str(REALTIME_FIXTURE),
            start_collector=False,
        )
        collector = app.state.collector
        self.assertTrue(collector.start())
        self.assertFalse(collector.start())
        collector.stop()

    def test_validation_uses_only_stored_history(self):
        result = run_validation(self.database, "realtime", self.root / "验证")
        self.assertEqual(result["validation_status"], "insufficient_intraday_history")
        self.assertEqual(result["data_policy"], "stored_intraday_snapshots_only")
        self.assertTrue(Path(result["json_output"]).exists())
        header = Path(result["csv_output"]).read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("验证模式", header)

    def test_api_reads_while_realtime_writer_upserts(self):
        app = create_app(
            self.settings, self.database, self.logger, start_collector=False
        )

        def write_once():
            return RealtimePipeline(
                self.settings, self.database, self.logger
            ).run(now(15, 10), fixture=str(REALTIME_FIXTURE))[0]

        with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(write_once)
            statuses = [client.get("/api/v1/realtime").status_code for _ in range(10)]
            self.assertIsNotNone(future.result(timeout=10))
        self.assertEqual(statuses, [200] * 10)


if __name__ == "__main__":
    unittest.main()
