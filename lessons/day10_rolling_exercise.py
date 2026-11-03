"""Day 10: reproduce one rolling forecast from 20 already observed returns.

Run this completed worked example with:
    python lessons/day10_rolling_exercise.py

The script reads local inputs and compares the calculation with the saved
research forecast. It does not write files or download data.
"""

import csv
import json
import math
from pathlib import Path


def mean_squared_return(returns):
    """Return the arithmetic mean of the supplied decimal returns' squares."""
    if not returns:
        raise ValueError("At least one return is required.")

    # Square each return before averaging so opposite signs do not cancel.
    squared_returns = [r * r for r in returns]

    # This is a mean of squares: divide by the number of observations.
    forecast = sum(squared_returns) / len(squared_returns)

    return forecast


def main():
    lesson_dir = Path(__file__).resolve().parent
    input_path = lesson_dir / "day10_rolling_inputs.json"
    exercise = json.loads(input_path.read_text(encoding="utf-8-sig"))
    intervals = exercise["input_intervals"]
    returns = [interval["simple_return"] for interval in intervals]

    print("Day 10: one rolling mean-of-squares forecast")
    print(f"Input returns: {len(returns)} (window: {exercise['window']})")
    print(
        f"First input interval: {intervals[0]['previous_date']} "
        f"to {intervals[0]['date']}"
    )
    print(
        f"Last input interval:  {intervals[-1]['previous_date']} "
        f"to {intervals[-1]['date']}"
    )
    print(f"Forecast origin: {exercise['forecast_origin']}")
    print(f"Target date:     {exercise['target_date']}")

    forecast = mean_squared_return(returns)

    # Read the saved result only after you have calculated your own forecast.
    reference_path = lesson_dir.parent / exercise["source_forecasts_csv"]
    with reference_path.open(encoding="utf-8-sig", newline="") as handle:
        reference = next(
            row for row in csv.DictReader(handle)
            if row["date"] == exercise["target_date"]
        )
    expected = float(reference["rolling_forecast"])
    matches = math.isclose(forecast, expected, rel_tol=1e-12, abs_tol=1e-15)

    print(f"\nYour forecast:  {forecast:.16g} squared decimal return")
    print(f"Saved forecast: {expected:.16g} squared decimal return")
    print(f"Matches the saved forecast: {matches}")
    if forecast >= 0:
        print(
            "Square root (approximate standard deviation under a zero-mean "
            f"assumption): {math.sqrt(forecast):.4%}"
        )
        print("The horizon is the next published interval; this describes magnitude.")
        print("Calendar gaps can differ across observed intervals.")


if __name__ == "__main__":
    main()
