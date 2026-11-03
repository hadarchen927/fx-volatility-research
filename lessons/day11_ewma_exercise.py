"""Day 11: a completed EWMA update after observing a new return.

Run from the project folder: python lessons/day11_ewma_exercise.py
This example reads local files and leaves the research model unchanged.
"""

import csv
import json
import math
from pathlib import Path


def ewma_update(previous_forecast, observed_return, decay):
    """Use the newly observed return to form the next interval's forecast."""
    # Square the newly observed decimal return.
    squared_return = observed_return * observed_return

    # Blend the old forecast and new square; the two weights add to one.
    next_forecast = decay * previous_forecast + (1 - decay) * squared_return

    return next_forecast


def main():
    lesson_dir = Path(__file__).resolve().parent
    input_path = lesson_dir / "day11_ewma_inputs.json"
    exercise = json.loads(input_path.read_text(encoding="utf-8-sig"))
    previous_forecast = exercise["previous_forecast"]
    observed_return = exercise["observed_return"]
    decay = exercise["decay"]

    print("Day 11: one EWMA update")
    print(f"Previous forecast origin: {exercise['previous_forecast_origin']}")
    print(f"Newly observed return date: {exercise['observed_return_date']}")
    print(f"Next forecast origin:     {exercise['next_forecast_origin']}")
    print(f"Next target date:         {exercise['next_target_date']}")
    print(f"\nPrevious forecast: {previous_forecast:.16g} squared decimal return")
    print(f"Observed return:   {observed_return:.16g} ({observed_return:.4%})")
    print(f"Decay:             {decay:g}")
    print(
        f"\nThe return ending {exercise['observed_return_date']} is now available."
    )
    print(
        f"Use it to update the forecast for the interval ending "
        f"{exercise['next_target_date']}."
    )
    print("The forecast for the newly observed interval was made earlier.")

    next_forecast = ewma_update(previous_forecast, observed_return, decay)

    # Check the next target's saved forecast only after calculating your update.
    reference_path = lesson_dir.parent / exercise["source_forecasts_csv"]
    with reference_path.open(encoding="utf-8-sig", newline="") as handle:
        reference = next(
            row for row in csv.DictReader(handle)
            if row["date"] == exercise["next_target_date"]
        )
    expected = float(reference["ewma_forecast"])
    matches = math.isclose(next_forecast, expected, rel_tol=1e-12, abs_tol=1e-15)

    print(f"\nYour next forecast:  {next_forecast:.16g} squared decimal return")
    print(f"Saved next forecast: {expected:.16g} squared decimal return")
    print(f"Matches the saved forecast: {matches}")
    if next_forecast < previous_forecast:
        change = "decreased"
    elif next_forecast > previous_forecast:
        change = "increased"
    else:
        change = "stayed the same"
    print(f"Compared with the previous forecast, the squared-return forecast {change}.")
    print("This change describes forecast magnitude; it does not predict price direction.")


if __name__ == "__main__":
    main()
