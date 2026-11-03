"""Hand-calculated checks for the completed EWMA and MSE learning examples."""

from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from lessons.day11_ewma_exercise import ewma_update
from lessons.day12_mse_comparison import (
    mean_squared_error,
    relative_mse_change,
    squared_error,
)


class EwmaLearningTests(unittest.TestCase):
    def test_one_update_has_a_hand_calculated_result(self):
        # Old forecast 0.04; new squared return 0.01; weights 3/4 and 1/4.
        self.assertAlmostEqual(ewma_update(0.04, 0.1, 0.75), 0.0325)

    def test_equal_magnitude_returns_have_the_same_update(self):
        positive = ewma_update(0.001, 0.02, 0.94)
        negative = ewma_update(0.001, -0.02, 0.94)
        self.assertEqual(positive, negative)


class MseLearningTests(unittest.TestCase):
    def test_squared_error_penalizes_equal_errors_in_both_directions(self):
        self.assertAlmostEqual(squared_error(0.04, 0.01), 0.0009)
        self.assertAlmostEqual(squared_error(0.01, 0.04), 0.0009)
        self.assertEqual(squared_error(0.02, 0.02), 0.0)

    def test_mean_uses_every_paired_loss_including_zero(self):
        # The three losses are 0.01, 0 and 0.04: their mean is 1/60.
        self.assertAlmostEqual(
            mean_squared_error([0.1, 0.2, 0.3], [0.2, 0.2, 0.1]), 1 / 60
        )

    def test_empty_or_unequal_lists_raise_value_error(self):
        for forecasts, targets in (([], []), ([], [1]), ([1], []), ([1, 2], [1])):
            with self.subTest(forecasts=forecasts, targets=targets):
                with self.assertRaises(ValueError):
                    mean_squared_error(forecasts, targets)

    def test_relative_change_sign_identifies_the_lower_mse(self):
        self.assertEqual(relative_mse_change(4, 3), -0.25)
        self.assertAlmostEqual(relative_mse_change(3, 4), 1 / 3)
        self.assertEqual(relative_mse_change(4, 4), 0)

    def test_zero_baseline_has_no_relative_change(self):
        self.assertIsNone(relative_mse_change(0, 0))
        self.assertIsNone(relative_mse_change(0, 1))


if __name__ == "__main__":
    unittest.main()
