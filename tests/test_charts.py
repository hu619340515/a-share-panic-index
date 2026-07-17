"""v4 图表单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from viz.charts import Visualizer
import matplotlib.pyplot as plt

from scripts.a_share_panic_index.charting import _load_trading_snapshots


class TestVisualizer(unittest.TestCase):
    def setUp(self):
        index = pd.date_range("2026-06-01", periods=30, freq="B")
        values = np.linspace(30, 88, len(index))
        self.frame = pd.DataFrame(
            {
                "panic_index": values,
                "status": ["中性"] * 29 + ["极度恐慌"],
                "quality_status": ["final"] * 30,
                "threshold_p05": np.linspace(12, 14, len(index)),
                "threshold_p25": np.linspace(28, 30, len(index)),
                "threshold_p75": np.linspace(65, 68, len(index)),
                "threshold_p95": np.linspace(84, 86, len(index)),
                "volatility": np.linspace(0.18, 0.35, len(index)),
                "limit_up": np.arange(30) + 20,
                "limit_down": np.arange(30)[::-1] + 5,
                "southbound_flow": np.linspace(-30, 45, len(index)),
            },
            index=index,
        )
        self.raw_data = {
            "hs300": pd.Series(np.linspace(3900, 4500, len(index)), index=index)
        }

    def test_comprehensive_chart_contains_all_v4_panels(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "chart.png"
            visualizer = Visualizer(
                {"dpi": 72, "figure_size": [10, 14], "style": "default"}
            )
            visualizer.plot_comprehensive(self.frame, self.raw_data, str(output))
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 20_000)

    def test_volatility_column_is_rendered_as_percent(self):
        visualizer = Visualizer({"style": "default"})
        fig, ax = plt.subplots()
        visualizer._plot_volatility(ax, self.frame)
        self.assertEqual(ax.get_title(), "沪深300 20日年化波动率")
        self.assertEqual(len(ax.lines), 1)
        self.assertAlmostEqual(float(ax.lines[0].get_ydata()[-1]), 35.0)
        plt.close(fig)

    def test_x_axis_compresses_weekend_but_keeps_date_labels(self):
        frame = self.frame.iloc[:2].copy()
        frame.index = pd.to_datetime(["2026-07-10", "2026-07-13"])
        visualizer = Visualizer({"style": "default"})
        fig, ax = plt.subplots()
        visualizer._plot_panic_index(ax, frame)
        visualizer._format_trading_dates(ax, frame.index)
        self.assertEqual(list(ax.lines[0].get_xdata()), [0.0, 1.0])
        labels = [label.get_text() for label in ax.get_xticklabels()]
        self.assertEqual(labels, ["2026-07-10", "2026-07-13"])
        plt.close(fig)

    def test_snapshot_window_keeps_latest_120_trading_days(self):
        index = pd.date_range("2025-12-01", periods=190, freq="D")
        snapshots = pd.DataFrame({"panic_index": np.arange(len(index))}, index=index)

        class Database:
            @staticmethod
            def load_snapshots(days):
                return snapshots.tail(days)

        class Calendar:
            @staticmethod
            def is_session(value):
                return value.weekday() < 5

        result = _load_trading_snapshots(Database(), Calendar(), 120)
        self.assertEqual(len(result), 120)
        self.assertTrue(all(date.weekday() < 5 for date in result.index))
        self.assertEqual(result.index[-1], snapshots.index[-1])


if __name__ == "__main__":
    unittest.main()
