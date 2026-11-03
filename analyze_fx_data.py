"""Days 5-6: calculate, describe and plot consecutive ECB observation returns.

Run the Day 4 audit first. No observations are inserted on unpublished dates.
CSV returns are decimals; the console and chart display percentages.
The whole-sample mean describes the inspection sample; it is not a forecast.
"""

import csv
import hashlib
import json
import math
import platform
from datetime import date
from pathlib import Path
from statistics import mean

from audit_fx_data import main as audit_data
from fx_calculator import simple_return


PROJECT_DIR = Path(__file__).resolve().parent
FILE_STEM = "eur_usd_2024-01-01_2024-01-31"
DATA_FILE = PROJECT_DIR / "data" / "processed" / f"{FILE_STEM}.csv"
RETURNS_FILE = DATA_FILE.with_name(f"{FILE_STEM}_returns.csv")
FIGURE_FILE = PROJECT_DIR / "reports" / "fx_overview.png"
SUMMARY_FILE = PROJECT_DIR / "reports" / "return_summary.json"
RETURN_COLUMNS = [
    "previous_date", "date", "calendar_gap_days",
    "previous_usd_per_eur", "usd_per_eur", "simple_return",
]


def load_observations(path):
    """Read the audited dates and exchange rates in their existing order."""
    with path.open(newline="", encoding="utf-8-sig") as source_file:
        return [
            {"date": date.fromisoformat(row["date"]),
             "usd_per_eur": float(row["usd_per_eur"])}
            for row in csv.DictReader(source_file)
        ]


def calculate_returns(observations):
    """Create one return row per pair of consecutive observations."""
    if len(observations) < 2:
        raise ValueError("At least two observations are needed for a return.")

    returns = []
    for previous, current in zip(observations, observations[1:]):
        gap_days = (current["date"] - previous["date"]).days
        if gap_days <= 0:
            raise ValueError("Observation dates must be strictly increasing.")
        if not all(
            math.isfinite(rate) and rate > 0
            for rate in (previous["usd_per_eur"], current["usd_per_eur"])
        ):
            raise ValueError("Exchange rates must be positive and finite.")

        returns.append({
            "previous_date": previous["date"].isoformat(),
            "date": current["date"].isoformat(),
            "calendar_gap_days": gap_days,
            "previous_usd_per_eur": previous["usd_per_eur"],
            "usd_per_eur": current["usd_per_eur"],
            "simple_return": simple_return(
                previous["usd_per_eur"], current["usd_per_eur"]
            ),
        })
    return returns


def describe_returns(returns):
    """Summarise the observed intervals, which have mixed calendar lengths."""
    values = [row["simple_return"] for row in returns]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("Descriptive statistics need non-empty, finite returns.")
    return {
        "mean_interval_simple_return": mean(values),
        "positive_interval_count": sum(value > 0 for value in values),
        "negative_interval_count": sum(value < 0 for value in values),
        "zero_interval_count": sum(value == 0 for value in values),
    }


def save_returns(returns, path):
    """Keep numerical returns as decimals, with explicit start and end dates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=RETURN_COLUMNS)
        writer.writeheader()
        writer.writerows(returns)


def save_plot(observations, returns, path):
    """Save a figure using actual calendar dates on both horizontal axes."""
    import matplotlib

    # Save the figure without opening a GUI window.
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter, PercentFormatter

    quote_dates = [row["date"] for row in observations]
    quote_values = [row["usd_per_eur"] for row in observations]
    return_dates = [date.fromisoformat(row["date"]) for row in returns]
    return_values = [row["simple_return"] for row in returns]

    with plt.rc_context({"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False}):
        figure, axes = plt.subplots(
            2, 1, figsize=(12, 7), sharex=True,
            gridspec_kw={"height_ratios": [1.1, 1]},
        )
        figure.subplots_adjust(left=0.10, right=0.97, bottom=0.16, top=0.88, hspace=0.30)
        figure.suptitle("EUR/USD | January 2024", x=0.10, ha="left", fontsize=20)

        axes[0].plot(quote_dates, quote_values, color="#203864", linewidth=1.8,
                     marker="o", markersize=4)
        axes[0].set_title("ECB reference rate", loc="left", fontsize=12)
        axes[0].set_ylabel("USD per EUR")
        axes[0].yaxis.set_major_formatter(FormatStrFormatter("%.3f"))

        colors = ["#087f8c" if value >= 0 else "#b64747" for value in return_values]
        axes[1].bar(return_dates, return_values, width=0.75, color=colors, zorder=3)
        axes[1].axhline(0, color="#505050", linewidth=0.8)
        sample_mean = mean(return_values)
        axes[1].axhline(
            sample_mean, color="#935a00", linestyle="--", linewidth=1.5,
            label=f"Full-sample mean (descriptive): {sample_mean:+.4%}", zorder=4,
        )
        axes[1].legend(loc="lower right", bbox_to_anchor=(1.0, 1.01),
                       fontsize=9, frameon=False, borderaxespad=0)
        axes[1].set_title("Observation-interval returns and sample mean", loc="left", fontsize=12)
        axes[1].set_ylabel("Return (%)")
        axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=2))
        axes[1].set_xlabel("Observation date, 2024 (return dated at the interval's end)")
        axes[1].xaxis.set_major_locator(mdates.DayLocator(bymonthday=[2, 8, 15, 22, 29, 31]))
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        for axis in axes:
            axis.grid(axis="y", color="#dedede", linewidth=0.7, zorder=0)
            axis.set_axisbelow(True)

        figure.text(
            0.10, 0.035,
            "Source: European Central Bank. 22 quotes, 21 interval returns. Mean uses all 21 returns (descriptive).\n"
            "Markers show published observations; connecting lines do not show intraday paths. Calendar gaps are preserved.",
            fontsize=9, color="#555555", ha="left",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=180, facecolor="white")
        plt.close(figure)


def main():
    print("Checking the source table with the Day 4 audit:")
    audit_data()
    observations = load_observations(DATA_FILE)
    returns = calculate_returns(observations)
    descriptive = describe_returns(returns)

    # Compounding consecutive returns must recover the first-to-last change.
    sample_change = simple_return(
        observations[0]["usd_per_eur"], observations[-1]["usd_per_eur"]
    )
    compounded_change = math.prod(1 + row["simple_return"] for row in returns) - 1
    if not math.isclose(sample_change, compounded_change, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Return compounding did not match the sample's endpoint change.")

    save_returns(returns, RETURNS_FILE)
    save_plot(observations, returns, FIGURE_FILE)

    import matplotlib

    summary = {
        "source": "European Central Bank, EXR.D.USD.EUR.SP00.A",
        "quote_units": "US dollars per one euro",
        "return_units": "Decimal simple return between consecutive published observations",
        "input_csv_sha256": hashlib.sha256(DATA_FILE.read_bytes()).hexdigest(),
        "quote_count": len(observations),
        "return_count": len(returns),
        "first_observation_date": observations[0]["date"].isoformat(),
        "last_observation_date": observations[-1]["date"].isoformat(),
        "first_to_last_reference_rate_change": sample_change,
        "intervals_longer_than_one_calendar_day": sum(row["calendar_gap_days"] > 1 for row in returns),
        **descriptive,
        "mean_interpretation": "Arithmetic sample mean per observed interval, with mixed calendar lengths; descriptive, not a forecast.",
        "python_version": platform.python_version(),
        "matplotlib_version": matplotlib.__version__,
        "limitations": "One-month inspection sample; reference rates are not executable trading prices. No predictive model has been evaluated.",
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"\nQuotes: {len(observations)}; observation-interval returns: {len(returns)}")
    print("First five returns:")
    for row in returns[:5]:
        print(f"{row['previous_date']} -> {row['date']}: "
              f"{row['simple_return']:+.4%} ({row['calendar_gap_days']} calendar day(s))")
    print(f"Sample mean return per observation interval: {descriptive['mean_interval_simple_return']:+.4%}")
    print(f"Positive / negative / zero intervals: {descriptive['positive_interval_count']} / "
          f"{descriptive['negative_interval_count']} / {descriptive['zero_interval_count']}")
    print("The mean describes this sample of mixed-length intervals; it is not a forecast.")
    print(f"Reference-rate change, first to last observation: {sample_change:+.4%}")
    print(f"Returns CSV: {RETURNS_FILE}")
    print(f"Figure: {FIGURE_FILE}")
    print(f"Summary: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
