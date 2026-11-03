"""Deterministic tests of interval alignment, forecast timing, and model losses."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from forecast_models import forecast_returns, make_interval_returns, mse_comparison


def interval_records(values):
    """Build a contiguous daily interval sequence with known simple returns."""
    start = date(2024, 1, 1)
    return [
        {
            "previous_date": (start + timedelta(days=index)).isoformat(),
            "date": (start + timedelta(days=index + 1)).isoformat(),
            "calendar_gap_days": 1,
            "simple_return": value,
            "target_squared_return": value * value,
        }
        for index, value in enumerate(values)
    ]


class IntervalReturnTests(unittest.TestCase):
    def test_consecutive_quotes_preserve_weekend_gap_without_scaling(self):
        quotes = [
            {"date": "2024-01-05", "usd_per_eur": 2.0},
            {"date": "2024-01-08", "usd_per_eur": 3.0},
            {"date": "2024-01-09", "usd_per_eur": 1.5},
        ]
        before = deepcopy(quotes)
        self.assertEqual(
            make_interval_returns(quotes),
            [
                {
                    "previous_date": "2024-01-05",
                    "date": "2024-01-08",
                    "calendar_gap_days": 3,
                    "simple_return": 0.5,
                    "target_squared_return": 0.25,
                },
                {
                    "previous_date": "2024-01-08",
                    "date": "2024-01-09",
                    "calendar_gap_days": 1,
                    "simple_return": -0.5,
                    "target_squared_return": 0.25,
                },
            ],
        )
        self.assertEqual(quotes, before)

    def test_short_quote_history_has_no_interval(self):
        self.assertEqual(make_interval_returns([]), [])
        self.assertEqual(
            make_interval_returns([{"date": "2024-01-01", "usd_per_eur": 1.0}]), []
        )

    def test_bad_quotes_raise_value_error(self):
        bad_quote_lists = [
            None,
            "quotes",
            [None],
            [{}],
            [{"date": "20240101", "usd_per_eur": 1}],
            [{"date": "2024-02-30", "usd_per_eur": 1}],
        ]
        for value in (0, -1, True, "1.0", float("nan"), float("inf")):
            bad_quote_lists.append([{"date": "2024-01-01", "usd_per_eur": value}])
        for dates in (("2024-01-01", "2024-01-01"), ("2024-01-02", "2024-01-01")):
            bad_quote_lists.append([{"date": day, "usd_per_eur": 1} for day in dates])
        for quotes in bad_quote_lists:
            with self.subTest(quotes=quotes), self.assertRaises(ValueError):
                make_interval_returns(quotes)


class ForecastTests(unittest.TestCase):
    def test_hand_sequence_forecasts_before_seeing_current_target(self):
        returns = interval_records([0.1, 0.2, 0.3, 0.4])
        returns[2]["source"] = "teaching example"
        before = deepcopy(returns)
        forecasts = forecast_returns(returns, window=2, decay=0.5)
        self.assertEqual(len(forecasts), 2)
        first, second = forecasts
        self.assertEqual(first["date"], "2024-01-04")
        self.assertEqual(first["forecast_origin"], "2024-01-03")
        self.assertEqual(first["source"], "teaching example")
        self.assertAlmostEqual(first["rolling_forecast"], 0.025)
        self.assertAlmostEqual(first["ewma_forecast"], 0.025)
        self.assertAlmostEqual(first["rolling_loss"], (0.025 - 0.09) ** 2)
        self.assertAlmostEqual(first["ewma_loss"], (0.025 - 0.09) ** 2)
        self.assertAlmostEqual(second["rolling_forecast"], 0.065)
        self.assertAlmostEqual(second["ewma_forecast"], 0.0575)
        self.assertAlmostEqual(second["ewma_loss"], (0.0575 - 0.16) ** 2)
        self.assertEqual(returns, before)

    def test_ewma_recursion_uses_each_target_after_its_forecast(self):
        forecasts = forecast_returns(
            interval_records([0.1, -0.2, 0.3, -0.4, 0.5]), window=2, decay=0.8
        )
        for forecast, expected in zip(forecasts, (0.025, 0.038, 0.0624)):
            self.assertAlmostEqual(forecast["ewma_forecast"], expected)
        for forecast, expected in zip(forecasts, (0.025, 0.065, 0.125)):
            self.assertAlmostEqual(forecast["rolling_forecast"], expected)

    def test_future_perturbation_preserves_earlier_forecasts(self):
        baseline = interval_records([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        changed = interval_records([0.1, 0.2, 0.3, 0.4, 0.8, 0.6])
        original_forecasts = forecast_returns(baseline, window=2)
        changed_forecasts = forecast_returns(changed, window=2)
        self.assertEqual(original_forecasts[:2], changed_forecasts[:2])
        for key in ("rolling_forecast", "ewma_forecast"):
            self.assertEqual(original_forecasts[2][key], changed_forecasts[2][key])
            self.assertNotEqual(original_forecasts[3][key], changed_forecasts[3][key])
        self.assertNotEqual(
            original_forecasts[2]["ewma_loss"], changed_forecasts[2]["ewma_loss"]
        )

    def test_forecasts_keep_an_observed_multiday_target_interval(self):
        quotes = [
            {"date": "2024-01-03", "usd_per_eur": 1.0},
            {"date": "2024-01-04", "usd_per_eur": 1.1},
            {"date": "2024-01-05", "usd_per_eur": 1.21},
            {"date": "2024-01-08", "usd_per_eur": 1.331},
        ]
        forecast = forecast_returns(make_interval_returns(quotes), window=2)[0]
        self.assertEqual(forecast["forecast_origin"], "2024-01-05")
        self.assertEqual(forecast["calendar_gap_days"], 3)
        self.assertAlmostEqual(forecast["target_squared_return"], 0.01)
        self.assertAlmostEqual(forecast["rolling_forecast"], 0.01)

    def test_exact_flat_quotes_give_zero_forecasts_and_losses(self):
        quotes = [
            {"date": f"2024-01-{day:02d}", "usd_per_eur": 1.25}
            for day in range(1, 7)
        ]
        forecasts = forecast_returns(make_interval_returns(quotes), window=2)
        self.assertEqual(len(forecasts), 3)
        for forecast in forecasts:
            for key in (
                "simple_return", "target_squared_return", "rolling_forecast",
                "ewma_forecast", "rolling_loss", "ewma_loss",
            ):
                self.assertEqual(forecast[key], 0.0)
        self.assertEqual(
            mse_comparison(forecasts),
            {"count": 3, "rolling_mse": 0.0, "ewma_mse": 0.0,
             "ewma_relative_mse_change": None},
        )

    def test_invalid_parameters_and_insufficient_history_raise_value_error(self):
        returns = interval_records([0.1, 0.2, 0.3])
        for window in (True, False, 0, -1, 1.5, "2", None):
            with self.subTest(window=window), self.assertRaises(ValueError):
                forecast_returns(returns, window=window)
        for decay in (True, False, 0, 1, -0.1, 1.1, "0.9", None,
                      float("nan"), float("inf"), -float("inf")):
            with self.subTest(decay=decay), self.assertRaises(ValueError):
                forecast_returns(returns, window=2, decay=decay)
        for history in ([], returns[:1], returns[:2]):
            with self.subTest(history=history), self.assertRaisesRegex(
                ValueError, "At least 3 interval returns"
            ):
                forecast_returns(history, window=2)

    def test_invalid_or_inconsistent_returns_raise_value_error(self):
        original = interval_records([0.1, 0.2, 0.3])
        for field, bad_value in (
            ("previous_date", "2024-01-05"),
            ("date", "2024-01-01"),
            ("date", "20240103"),
            ("calendar_gap_days", 2),
            ("calendar_gap_days", True),
            ("simple_return", float("nan")),
            ("simple_return", float("inf")),
            ("simple_return", True),
            ("simple_return", -1),
            ("target_squared_return", -0.1),
            ("target_squared_return", float("inf")),
            ("target_squared_return", 0.25),
        ):
            changed = deepcopy(original)
            changed[1][field] = bad_value
            with self.subTest(field=field, value=bad_value), self.assertRaises(ValueError):
                forecast_returns(changed, window=2)
        discontinuous = deepcopy(original)
        discontinuous[1]["previous_date"] = "2024-01-01"
        discontinuous[1]["calendar_gap_days"] = 2
        for records in (None, "returns", [None], [{}], discontinuous, original[::-1]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                forecast_returns(records, window=2)


class MseComparisonTests(unittest.TestCase):
    def test_negative_relative_change_favors_ewma(self):
        result = mse_comparison([
            {"rolling_loss": 4, "ewma_loss": 1},
            {"rolling_loss": 16, "ewma_loss": 9},
        ])
        self.assertEqual(
            result,
            {"count": 2, "rolling_mse": 10.0, "ewma_mse": 5.0,
             "ewma_relative_mse_change": -0.5},
        )
        self.assertEqual(
            mse_comparison([{"rolling_loss": 1, "ewma_loss": 2}])[
                "ewma_relative_mse_change"
            ],
            1.0,
        )

    def test_zero_rolling_mse_has_undefined_relative_change(self):
        result = mse_comparison([{"rolling_loss": 0, "ewma_loss": 1}])
        self.assertIsNone(result["ewma_relative_mse_change"])

    def test_invalid_losses_raise_value_error(self):
        for records in (
            [], None, [None], [{}],
            [{"rolling_loss": -1, "ewma_loss": 1}],
            [{"rolling_loss": 1, "ewma_loss": float("nan")}],
            [{"rolling_loss": float("inf"), "ewma_loss": 1}],
            [{"rolling_loss": True, "ewma_loss": 1}],
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                mse_comparison(records)


class ImportTests(unittest.TestCase):
    def test_import_is_silent_and_does_not_create_working_files(self):
        code = f"import sys; sys.path.insert(0, {str(MODULE_DIR)!r}); import forecast_models"
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-B", "-c", code], cwd=directory,
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
