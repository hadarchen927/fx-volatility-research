"""Day 12: score two worked examples, then verify the full final-period MSE.

Run from the project folder: python lessons/day12_mse_comparison.py
Only saved CSV and JSON files are read. No forecasts or study files change.
"""

import csv
from itertools import islice
import json
import math
from pathlib import Path


def squared_error(forecast, target):
    """Score a squared-return forecast after its target has been observed."""
    error = forecast - target
    return error * error


def mean_squared_error(forecasts, targets):
    """Average paired squared errors; both lists must have the same positive size."""
    if len(forecasts) != len(targets):
        raise ValueError("Forecasts and targets must have the same length.")
    if not forecasts:
        raise ValueError("At least one forecast and target are required.")
    losses = [
        squared_error(forecast, target)
        for forecast, target in zip(forecasts, targets)
    ]
    return sum(losses) / len(losses)


def relative_mse_change(rolling_mse, ewma_mse):
    """Return EWMA / rolling MSE - 1; None means a zero rolling baseline."""
    if rolling_mse == 0:
        return None
    return ewma_mse / rolling_mse - 1


def main():
    project_dir = Path(__file__).resolve().parents[1]
    report_dir = project_dir / "reports" / "research"
    with (report_dir / "development_forecasts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        examples = list(islice(csv.DictReader(handle), 2))
    if len(examples) != 2:
        raise ValueError("The worked example needs the first two development rows.")

    print("Day 12: losses and mean squared error")
    print("A saved forecast is scored after its squared-return target is observed.")
    print("Forecasts and targets have units of squared decimal return.")
    print("Their squared-error losses and MSE have units of decimal return to the fourth power.")
    for row in examples:
        target = float(row["target_squared_return"])
        rolling = float(row["rolling_forecast"])
        ewma = float(row["ewma_forecast"])
        print(f"\nTarget date: {row['date']} (forecast origin: {row['forecast_origin']})")
        print(f"Observed squared return: {target:.12g}")
        print(f"Rolling forecast: {rolling:.12g}; loss: {squared_error(rolling, target):.12g}")
        print(f"EWMA forecast:    {ewma:.12g}; loss: {squared_error(ewma, target):.12g}")

    targets = [float(row["target_squared_return"]) for row in examples]
    rolling_forecasts = [float(row["rolling_forecast"]) for row in examples]
    ewma_forecasts = [float(row["ewma_forecast"]) for row in examples]
    rolling_mse = mean_squared_error(rolling_forecasts, targets)
    ewma_mse = mean_squared_error(ewma_forecasts, targets)
    relative = relative_mse_change(rolling_mse, ewma_mse)
    relative_text = "undefined (zero rolling MSE)" if relative is None else f"{relative:+.2%}"
    print(f"\nTwo-example rolling MSE: {rolling_mse:.12g}")
    print(f"Two-example EWMA MSE:    {ewma_mse:.12g}")
    print(f"Two-example relative MSE change: {relative_text}")
    print("These two worked examples are a small teaching sample.")

    # Recalculate the whole final split separately, using the saved forecasts.
    with (report_dir / "final_forecasts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        final_rows = [row for row in csv.DictReader(handle) if row["split"] == "final"]
    targets = [float(row["target_squared_return"]) for row in final_rows]
    rolling_forecasts = [float(row["rolling_forecast"]) for row in final_rows]
    ewma_forecasts = [float(row["ewma_forecast"]) for row in final_rows]
    rolling_mse = mean_squared_error(rolling_forecasts, targets)
    ewma_mse = mean_squared_error(ewma_forecasts, targets)
    relative = relative_mse_change(rolling_mse, ewma_mse)
    relative_text = "undefined (zero rolling MSE)" if relative is None else f"{relative:+.2%}"
    summary = json.loads(
        (report_dir / "final_summary.json").read_text(encoding="utf-8-sig")
    )
    saved = summary["scores_by_split"]["final"]
    matches = (
        len(final_rows) == saved["count"]
        and math.isclose(rolling_mse, saved["rolling_mse"], rel_tol=1e-12, abs_tol=1e-20)
        and math.isclose(ewma_mse, saved["ewma_mse"], rel_tol=1e-12, abs_tol=1e-20)
    )
    print(f"\nFull 2025 final split: {len(final_rows)} targets")
    print(f"Full-period rolling MSE: {rolling_mse:.12g}")
    print(f"Full-period EWMA MSE:    {ewma_mse:.12g}")
    print(f"Full-period relative MSE change: {relative_text}")
    print(f"Count and both MSEs match the saved final summary: {matches}")
    print("A negative relative change favors EWMA; a positive change favors rolling.")
    print("This is a descriptive error comparison, not a prediction of price direction.")


if __name__ == "__main__":
    main()
