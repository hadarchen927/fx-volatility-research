"""Audit the January 2024 EUR/USD inspection sample."""

import csv
import json
import math
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DATA_FILE = (
    PROJECT_DIR / "data" / "processed"
    / "eur_usd_2024-01-01_2024-01-31.csv"
)
REPORT_FILE = PROJECT_DIR / "reports" / "data_quality_report.json"


def main():
    with DATA_FILE.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        required_columns = {"date", "usd_per_eur"}
        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError("Required columns are missing.")

        rows = list(reader)

    if not rows:
        raise ValueError("The dataset is empty.")

    # Keep the original order so we can detect ordering problems.
    dates = [date.fromisoformat(row["date"]) for row in rows]
    rates = [float(row["usd_per_eur"]) for row in rows]
    observed_dates = set(dates)

    # This calendar covers January 2024 only.
    calendar_dates = [date(2024, 1, day) for day in range(1, 32)]
    closing_dates = {date(2024, 1, 1)}

    expected_dates = {
        day for day in calendar_dates
        if day.weekday() < 5 and day not in closing_dates
    }

    missing_dates = sorted(expected_dates - observed_dates)
    unexpected_dates = sorted(observed_dates - expected_dates)

    checks = {
        "unique_dates": len(dates) == len(observed_dates),
        "chronological_order": all(
            previous < current
            for previous, current in zip(dates, dates[1:])
        ),
        "positive_finite_rates": all(
            math.isfinite(rate) and rate > 0
            for rate in rates
        ),
        "complete_publication_calendar": not missing_dates,
        "no_unexpected_dates": not unexpected_dates,
    }

    report = {
        "scope": "January 2024 EUR/USD inspection sample",
        "observed_rows": len(rows),
        "expected_observations": len(expected_dates),
        "checks": checks,
        "missing_dates": [day.isoformat() for day in missing_dates],
        "unexpected_dates": [day.isoformat() for day in unexpected_dates],
        "passed_all_checks": all(checks.values()),
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Observed rows: {len(rows)}")
    print(f"Expected observations: {len(expected_dates)}")

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")

    print(f"Missing publication dates: {report['missing_dates']}")
    print(f"Unexpected dates: {report['unexpected_dates']}")
    print(f"Report saved to: {REPORT_FILE}")

    if not report["passed_all_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()