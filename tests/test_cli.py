"""daily CLI 离线端到端测试。"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "daily_2026_07_17.json"


class TestDailyCLI(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_directory.name)
        self.database_path = self.temp_path / "panic_index.db"
        self.config_path = self.temp_path / "settings.yaml"
        self.config_path.write_text(
            """
database:
  rebuild_days: 730
  overlap_days: 40
logging:
  directory: ./logs
  retention_days: 3
  level: INFO
network:
  max_retries: 1
  retry_delay: 0
  provider_timeout: 1
  total_timeout: 20
market:
  calendar: XSHG
  timezone: Asia/Shanghai
  data_ready_time: '15:30'
""".strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def run_daily(
        self,
        target_date: str,
        root_entry: bool = False,
        fixture_path: Path = FIXTURE,
    ):
        environment = os.environ.copy()
        environment.update(
            {
                "PANIC_INDEX_FIXTURE_FILE": str(fixture_path),
                "PANIC_INDEX_DISABLE_SUBPROCESS": "1",
                "PANIC_INDEX_NOW": f"{target_date}T16:00:00+08:00",
            }
        )
        entry = PROJECT_ROOT / ("cli.py" if root_entry else "scripts/cli.py")
        return subprocess.run(
            [
                sys.executable,
                str(entry),
                "daily",
                "--date",
                target_date,
                "--config",
                str(self.config_path),
                "--database",
                str(self.database_path),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def test_daily_outputs_single_json_and_persists_provisional_result(self):
        completed = self.run_daily("2026-07-17")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1)

        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "success_provisional")
        self.assertEqual(payload["as_of_date"], "2026-07-17")
        self.assertEqual(payload["quality_status"], "provisional")
        self.assertLess(payload["result"]["components"]["volatility"], 1)
        self.assertAlmostEqual(
            payload["result"]["components"]["volatility_percent"], 35.0
        )
        self.assertIn("daily开始", completed.stderr)

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT panic_index, quality_status FROM panic_index WHERE date='2026-07-17'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], "provisional")

    def test_root_cli_is_compatible(self):
        completed = self.run_daily("2026-07-17", root_entry=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["exit_code"], 0)

    def test_primary_history_reconciles_provisional_record(self):
        first = self.run_daily("2026-07-17")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["quality_status"], "provisional")

        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        providers = payload["providers"]
        providers["baostock_volatility"]["records"].append(
            {"date": "2026-07-17", "volatility": 0.34, "hs300_close": 4529.1}
        )
        providers["jrj_limit_ratio"]["records"].append(
            {"date": "2026-07-17", "limit_ratio": 0.58, "limit_up": 42, "limit_down": 58}
        )
        providers["sina_futures_basis"]["records"].append(
            {"date": "2026-07-17", "futures_basis": 0.055}
        )
        providers["eastmoney_southbound_history"]["records"].append(
            {"date": "2026-07-17", "southbound_flow": -18.0}
        )
        final_fixture = self.temp_path / "final.json"
        final_fixture.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        second = self.run_daily("2026-07-17", fixture_path=final_fixture)
        self.assertEqual(second.returncode, 0, second.stderr)
        second_payload = json.loads(second.stdout)
        self.assertEqual(second_payload["status"], "success")
        self.assertEqual(second_payload["quality_status"], "final")
        self.assertEqual(
            second_payload["sources"]["volatility"]["provider"],
            "baostock_volatility",
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                """
                SELECT source, provisional FROM raw_metrics
                WHERE date='2026-07-17' AND metric='volatility'
                """
            ).fetchone()
        self.assertEqual(row, ("baostock_volatility", 0))

    def test_stale_returns_previous_snapshot_and_exit_code_three(self):
        first = self.run_daily("2026-07-16")
        self.assertEqual(first.returncode, 0, first.stderr)

        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for provider in (
            "eastmoney_index_volatility",
            "eastmoney_limit_pool",
            "cffex_futures_basis",
            "eastmoney_southbound_summary",
        ):
            payload["providers"][provider]["records"] = []
        stale_fixture = self.temp_path / "stale.json"
        stale_fixture.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        completed = self.run_daily("2026-07-17", fixture_path=stale_fixture)
        self.assertEqual(completed.returncode, 3)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "stale")
        self.assertEqual(payload["as_of_date"], "2026-07-16")
        self.assertTrue(payload["retry"]["recommended"])
        self.assertEqual(payload["retry"]["after_seconds"], 900)

    def test_non_trading_day_returns_snapshot_without_network(self):
        first = self.run_daily("2026-07-10")
        self.assertEqual(first.returncode, 0, first.stderr)

        completed = self.run_daily("2026-07-11")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "skipped_non_trading_day")
        self.assertEqual(payload["as_of_date"], "2026-07-10")

    def test_invalid_config_returns_json_and_exit_code_two(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/cli.py"),
                "daily",
                "--config",
                str(self.temp_path / "missing.yaml"),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["status"], "configuration_error")

    def test_invalid_date_returns_json_and_exit_code_two(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/cli.py"),
                "daily",
                "--date",
                "2026-99-99",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "argument_error")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
