"""动态情绪模型单元测试。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import pandas as pd
import numpy as np
from pandas.testing import assert_series_equal

from scripts.a_share_panic_index import APP_VERSION
from scripts.a_share_panic_index.calculator import PanicIndexCalculator
from scripts.a_share_panic_index.database import Database
from scripts.a_share_panic_index.emotion import (
    DynamicEmotionClassifier,
    historical_percentile_series,
)
from scripts.a_share_panic_index.config import Settings
from scripts.a_share_panic_index.runner import combine_observations


WEIGHTS = {
    "volatility": 0.4,
    "limit_up_down_ratio": 0.3,
    "futures_premium": 0.2,
    "southbound_flow": 0.1,
}


class TestHistoricalPercentile(unittest.TestCase):
    def test_current_and_future_values_are_excluded(self):
        base = pd.Series([1.0, 2.0, 3.0])
        base_result = historical_percentile_series(base, window=10)
        extended_result = historical_percentile_series(
            pd.concat([base, pd.Series([1000.0], index=[3])]),
            window=10,
        )

        self.assertAlmostEqual(base_result.iloc[0], 0.5)
        self.assertAlmostEqual(base_result.iloc[1], 0.75)
        self.assertAlmostEqual(base_result.iloc[2], 2.5 / 3)
        assert_series_equal(
            base_result,
            extended_result.iloc[:3],
            check_names=False,
        )

    def test_equal_history_values_remain_neutral(self):
        result = historical_percentile_series(pd.Series([3.0] * 8), window=5)
        self.assertTrue((result == 0.5).all())


class TestPanicScore(unittest.TestCase):
    def test_appending_future_extreme_does_not_rewrite_history(self):
        index = pd.bdate_range("2025-01-01", periods=260)
        frame = pd.DataFrame(
            {
                "volatility": [0.20 + position * 0.0001 for position in range(260)],
                "limit_ratio": [0.20 + position * 0.0002 for position in range(260)],
                "futures_basis": [0.01 + position * 0.00001 for position in range(260)],
                "southbound_flow": [100 - position * 0.1 for position in range(260)],
            },
            index=index,
        )
        calculator = PanicIndexCalculator(WEIGHTS, {"component_window": 504})
        base = calculator.calculate(frame)
        future = frame.copy()
        future.loc[index[-1] + pd.offsets.BDay()] = [5.0, 1.0, 1.0, -10000]
        extended = calculator.calculate(future)

        assert_series_equal(
            base["panic_index"],
            extended.loc[base.index, "panic_index"],
            check_freq=False,
        )

    def test_duplicate_dates_are_rejected(self):
        frame = pd.DataFrame(
            {
                "volatility": [0.2, 0.3],
                "limit_ratio": [0.2, 0.3],
                "futures_basis": [0.01, 0.02],
                "southbound_flow": [10, 5],
            },
            index=[pd.Timestamp("2026-07-17"), pd.Timestamp("2026-07-17")],
        )
        with self.assertRaisesRegex(ValueError, "重复日期"):
            PanicIndexCalculator(WEIGHTS).calculate(frame)

    def test_provisional_correction_recalculates_later_thresholds(self):
        dates = pd.bdate_range("2026-06-01", periods=20)
        records = []
        for position, value_date in enumerate(dates):
            metrics = {
                "volatility": 0.20 + position * 0.002,
                "limit_ratio": 0.20 + position * 0.01,
                "futures_basis": 0.01 + position * 0.001,
                "southbound_flow": 100 - position * 3,
            }
            for metric, value in metrics.items():
                records.append(
                    {
                        "date": value_date,
                        "metric": metric,
                        "value": value,
                        "source": "fixture_primary",
                        "provisional": False,
                        "fetched_at": pd.Timestamp("2026-07-17T16:00:00"),
                    }
                )
        provisional = pd.DataFrame(records)
        correction_date = dates[8]
        provisional.loc[
            provisional["date"].eq(correction_date),
            ["source", "provisional"],
        ] = ["fixture_fallback", True]

        corrections = {
            "volatility": 0.05,
            "limit_ratio": 0.01,
            "futures_basis": -0.20,
            "southbound_flow": 1000,
        }
        final = pd.DataFrame(
            [
                {
                    "date": correction_date,
                    "metric": metric,
                    "value": value,
                    "source": "fixture_primary",
                    "provisional": False,
                    "fetched_at": pd.Timestamp("2026-07-18T16:00:00"),
                }
                for metric, value in corrections.items()
            ]
        )

        config = {
            "component_window": 10,
            "min_periods": 5,
            "short_threshold_window": 5,
            "long_threshold_window": 10,
            "short_weight": 0.3,
            "long_weight": 0.7,
            "smoothing_span": 2,
        }

        def calculate(observations):
            values = observations.pivot(
                index="date", columns="metric", values="value"
            ).sort_index()
            scores = PanicIndexCalculator(WEIGHTS, config).calculate(values)
            return DynamicEmotionClassifier(config).classify(scores)

        before = calculate(provisional)
        merged = combine_observations(provisional, final)
        after = calculate(merged)

        assert_series_equal(
            before.loc[before.index < correction_date, "panic_index"],
            after.loc[after.index < correction_date, "panic_index"],
        )
        self.assertNotEqual(
            before.loc[correction_date, "panic_index"],
            after.loc[correction_date, "panic_index"],
        )
        self.assertNotEqual(
            before.iloc[-1]["threshold_p95"],
            after.iloc[-1]["threshold_p95"],
        )
        corrected = merged[
            merged["date"].eq(correction_date)
            & merged["metric"].eq("volatility")
        ].iloc[0]
        self.assertEqual(corrected["source"], "fixture_primary")
        self.assertFalse(bool(corrected["provisional"]))


class TestDynamicThresholds(unittest.TestCase):
    def setUp(self):
        self.config = {
            "min_periods": 3,
            "short_threshold_window": 2,
            "long_threshold_window": 4,
            "short_weight": 0.3,
            "long_weight": 0.7,
            "smoothing_span": 1,
            "quantiles": {
                "extreme_calm": 0.05,
                "calm": 0.25,
                "panic": 0.75,
                "extreme_panic": 0.95,
            },
            "trend": {
                "fast_change_threshold": 10,
                "slow_change_threshold": 3,
            },
        }

    def test_short_long_threshold_blend(self):
        frame = pd.DataFrame(
            {"panic_index": [10.0, 20.0, 30.0, 40.0, 50.0]},
            index=pd.bdate_range("2026-07-01", periods=5),
        )
        result = DynamicEmotionClassifier(self.config).classify(frame)

        short_p95 = pd.Series([30.0, 40.0]).quantile(0.95)
        long_p95 = pd.Series([10.0, 20.0, 30.0, 40.0]).quantile(0.95)
        expected = 0.3 * short_p95 + 0.7 * long_p95
        self.assertAlmostEqual(result.iloc[-1]["threshold_p95"], expected)
        self.assertEqual(result.iloc[-1]["classification_quality"], "final")
        self.assertEqual(result.iloc[-1]["model_version"], APP_VERSION)

    def test_current_score_does_not_change_its_threshold(self):
        index = pd.bdate_range("2026-07-01", periods=5)
        high = DynamicEmotionClassifier(self.config).classify(
            pd.DataFrame({"panic_index": [10, 20, 30, 40, 100]}, index=index)
        )
        low = DynamicEmotionClassifier(self.config).classify(
            pd.DataFrame({"panic_index": [10, 20, 30, 40, -100]}, index=index)
        )
        for column in ("threshold_p05", "threshold_p25", "threshold_p75", "threshold_p95"):
            self.assertAlmostEqual(high.iloc[-1][column], low.iloc[-1][column])

    def test_future_scores_do_not_rewrite_previous_thresholds(self):
        index = pd.bdate_range("2026-07-01", periods=6)
        base = pd.DataFrame({"panic_index": [10, 20, 30, 40, 50]}, index=index[:5])
        extended = pd.DataFrame(
            {"panic_index": [10, 20, 30, 40, 50, 1000]},
            index=index,
        )
        base_result = DynamicEmotionClassifier(self.config).classify(base)
        extended_result = DynamicEmotionClassifier(self.config).classify(extended)
        for column in (
            "panic_percentile",
            "threshold_p05",
            "threshold_p25",
            "threshold_p75",
            "threshold_p95",
            "status",
        ):
            assert_series_equal(
                base_result[column],
                extended_result.loc[base_result.index, column],
            )

    def test_boundaries_are_stateless_and_left_closed(self):
        thresholds = {"p05": 5, "p25": 25, "p75": 75, "p95": 95}
        classify = DynamicEmotionClassifier.classify_level
        self.assertEqual(classify(4.99, thresholds), "极度平静")
        self.assertEqual(classify(5, thresholds), "偏平静")
        self.assertEqual(classify(25, thresholds), "中性")
        self.assertEqual(classify(75, thresholds), "偏恐慌")
        self.assertEqual(classify(95, thresholds), "极度恐慌")
        self.assertEqual(classify(94, thresholds), "偏恐慌")

    def test_trend_and_transition_events_are_separate(self):
        classifier = DynamicEmotionClassifier(self.config)
        self.assertEqual(classifier.trend_label(1, 12), "快速升温")
        self.assertEqual(classifier.trend_label(-1, -5), "缓慢缓解")
        self.assertEqual(
            classifier.transition_event("偏恐慌", "极度恐慌"),
            "entered_extreme_panic",
        )
        self.assertEqual(
            classifier.transition_event("极度恐慌", "偏恐慌"),
            "exited_extreme_panic",
        )
        self.assertEqual(
            classifier.transition_event("中性", "中性", "快速升温"),
            "rapidly_heating",
        )
        self.assertEqual(
            classifier.transition_event("偏恐慌", "偏恐慌", "快速缓解"),
            "rapidly_cooling",
        )

    def test_ema_smoothing_is_causal(self):
        config = dict(self.config)
        config["smoothing_span"] = 3
        index = pd.bdate_range("2026-07-01", periods=2)
        result = DynamicEmotionClassifier(config).classify(
            pd.DataFrame({"panic_index": [10.0, 20.0]}, index=index)
        )
        self.assertAlmostEqual(result.iloc[0]["threshold_p95"], 95.0)
        self.assertAlmostEqual(result.iloc[1]["threshold_p95"], 52.5)

    def test_long_run_level_distribution_is_reasonable(self):
        generator = np.random.default_rng(20260717)
        scores = pd.Series(generator.normal(50, 12, size=1400)).clip(0, 100)
        frame = pd.DataFrame(
            {"panic_index": scores.to_numpy()},
            index=pd.bdate_range("2021-01-01", periods=len(scores)),
        )
        config = {
            "min_periods": 252,
            "short_threshold_window": 252,
            "long_threshold_window": 756,
            "short_weight": 0.3,
            "long_weight": 0.7,
            "smoothing_span": 20,
        }
        result = DynamicEmotionClassifier(config).classify(frame).iloc[756:]
        shares = result["status"].value_counts(normalize=True)

        self.assertTrue(0.02 <= shares.get("极度平静", 0) <= 0.08)
        self.assertTrue(0.12 <= shares.get("偏平静", 0) <= 0.30)
        self.assertTrue(0.40 <= shares.get("中性", 0) <= 0.60)
        self.assertTrue(0.12 <= shares.get("偏恐慌", 0) <= 0.30)
        self.assertTrue(0.02 <= shares.get("极度恐慌", 0) <= 0.08)


class TestEmotionSettings(unittest.TestCase):
    def test_default_dynamic_model_parameters(self):
        settings = Settings()
        model = settings.emotion_model
        database = settings.section("database")

        self.assertEqual(model["component_window"], 504)
        self.assertEqual(model["short_threshold_window"], 252)
        self.assertEqual(model["long_threshold_window"], 756)
        self.assertEqual(model["smoothing_span"], 20)
        self.assertEqual(model["quantiles"]["extreme_panic"], 0.95)
        self.assertNotIn("version", model)
        self.assertEqual(database["rebuild_days"], 1100)


class TestEmotionDatabase(unittest.TestCase):
    def test_emotion_audit_fields_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "panic.db")
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
                        "panic_index": 96.0,
                        "panic_percentile": 98.0,
                        "status": "极度恐慌",
                        "model_version": APP_VERSION,
                        "classification_quality": "final",
                        "threshold_p05": 20.0,
                        "threshold_p25": 30.0,
                        "threshold_p75": 60.0,
                        "threshold_p95": 90.0,
                        "change_1d": 6.0,
                        "change_5d": 15.0,
                        "percentile_change_1d": 4.0,
                        "percentile_change_5d": 12.0,
                        "trend": "快速升温",
                        "previous_level": "偏恐慌",
                        "level_changed": True,
                        "event": "entered_extreme_panic",
                        "volatility": 0.3,
                        "limit_ratio": 0.6,
                        "futures_basis": 0.04,
                        "southbound_flow": -20.0,
                        "quality_status": "final",
                        "sources": {},
                    }
                ],
                index=[pd.Timestamp("2026-07-17")],
            )
            database.persist(observations, panic_rows)
            snapshot = database.latest_snapshot()

            self.assertEqual(snapshot["model_version"], APP_VERSION)
            self.assertEqual(snapshot["emotion_level"], "极度恐慌")
            self.assertEqual(snapshot["event"], "entered_extreme_panic")
            self.assertEqual(snapshot["threshold_p95"], 90.0)
            with closing(sqlite3.connect(database.path)) as connection:
                version = connection.execute(
                    "SELECT value FROM metadata WHERE key='emotion_model_version'"
                ).fetchone()[0]
            self.assertEqual(version, APP_VERSION)


if __name__ == "__main__":
    unittest.main()
