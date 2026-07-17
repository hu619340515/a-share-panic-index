"""Hermes 图表 CLI 离线端到端测试。"""

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
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "chart_2026_07_17.json"


class TestChartCLI(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_directory.name)
        self.database_path = self.temp_path / "panic_index.db"
        self.output_path = self.temp_path / "恐慌指数.png"
        self.config_path = self.temp_path / "settings.yaml"
        self.config_path.write_text(
            """
database:
  rebuild_days: 1100
  overlap_days: 40
logging:
  directory: ./logs
network:
  max_retries: 1
  retry_delay: 0
  provider_timeout: 1
  total_timeout: 20
market:
  calendar: XSHG
  timezone: Asia/Shanghai
  data_ready_time: '15:30'
viz:
  dpi: 72
  figure_size: [10, 14]
  style: default
""".strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def run_chart(self, root_entry: bool = False, extra_args: list[str] | None = None):
        environment = os.environ.copy()
        environment.update(
            {
                "PANIC_INDEX_FIXTURE_FILE": str(FIXTURE),
                "PANIC_INDEX_DISABLE_SUBPROCESS": "1",
                "PANIC_INDEX_NOW": "2026-07-17T16:00:00+08:00",
                "PYTHONUTF8": "1",
            }
        )
        entry = PROJECT_ROOT / ("cli.py" if root_entry else "scripts/cli.py")
        arguments = [
            sys.executable,
            str(entry),
            "chart",
            "--date",
            "2026-07-17",
            "--config",
            str(self.config_path),
            "--database",
            str(self.database_path),
            "--output",
            str(self.output_path),
        ]
        arguments.extend(extra_args or [])
        return subprocess.run(
            arguments,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    def test_chart_outputs_single_json_and_image(self):
        completed = self.run_chart()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "chart_generated")
        self.assertEqual(payload["requested_trading_days"], 120)
        self.assertEqual(payload["trading_days"], 6)
        self.assertEqual(payload["as_of_date"], "2026-07-17")
        self.assertEqual(Path(payload["chart_path"]), self.output_path)
        self.assertTrue(self.output_path.exists())
        self.assertGreater(self.output_path.stat().st_size, 20_000)

        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM panic_index").fetchone()[0]
        self.assertGreater(count, 0)

    def test_root_entry_runs_same_chart_command(self):
        completed = self.run_chart(root_entry=True, extra_args=["--days", "5"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["requested_trading_days"], 5)
        self.assertEqual(payload["trading_days"], 5)

    def test_missing_config_returns_json_error(self):
        self.config_path.unlink()
        completed = self.run_chart()
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "configuration_error")

    def test_invalid_date_returns_json_error(self):
        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts/cli.py"), "chart", "--date", "bad"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "argument_error")

    def test_unsupported_commands_are_rejected(self):
        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts/cli.py"), "daily"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["status"], "argument_error")


if __name__ == "__main__":
    unittest.main()
