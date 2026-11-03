"""Reproduce the small FX forecasting study without changing the teaching files.

Development runs cannot read the final-period snapshot. A local protocol lock
records code/config hashes before the final-period download or evaluation.
This is a transparent local record, not an externally certified preregistration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from forecast_models import forecast_returns, make_interval_returns, mse_comparison
from research_data import audit_quotes, download_snapshot, load_snapshot


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "study_config.json"
REPORT_DIR = ROOT / "reports" / "research"
LOCK_PATH = REPORT_DIR / "protocol_lock.json"
LOCKED_FILES = ("study_config.json", "fx_calculator.py", "forecast_models.py", "research_data.py", "run_research.py")


def read_config(path=CONFIG_PATH):
    """The V1 protocol deliberately supports only the declared study choices."""
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    ordered = [config[k] for k in ("start_date", "development_end", "validation_start",
                                  "validation_end", "final_start", "end_date")]
    dates = [date.fromisoformat(value) for value in ordered]
    if any(parsed.isoformat() != original for parsed, original in zip(dates, ordered)):
        raise ValueError("Study dates must use canonical YYYY-MM-DD format.")
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("Study boundaries must be strictly chronological.")
    if dates[2].toordinal() != dates[1].toordinal() + 1 or dates[4].toordinal() != dates[3].toordinal() + 1:
        raise ValueError("Study splits must be adjacent calendar periods.")
    if config["target"] != "next_published_observation_squared_simple_return" or config["metric"] != "mean_squared_error":
        raise ValueError("Unsupported target or metric.")
    if config["calendar_gap_scaling"] != "none" or config["conditional_mean_assumption"] != "zero":
        raise ValueError("Unsupported return scaling or mean assumption.")
    window, decay = config["rolling_window"], config["ewma_decay"]
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("rolling_window must be a positive integer.")
    if isinstance(decay, bool) or not isinstance(decay, (float, int)) or not math.isfinite(decay) or not 0 < decay < 1:
        raise ValueError("ewma_decay must be strictly between zero and one.")
    return config


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_fingerprints(root=ROOT):
    return {name: sha256(Path(root) / name) for name in LOCKED_FILES}


def require_lock(lock_path=LOCK_PATH, root=ROOT):
    if not Path(lock_path).is_file():
        raise ValueError("Final evaluation needs a protocol lock: run --stage development --freeze first.")
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    if lock["file_sha256"] != code_fingerprints(root):
        raise ValueError("Protocol code/config changed after freezing. Preserve the original study; do not silently retune it.")
    return lock


def snapshot(start, end, offline):
    raw_dir = ROOT / "data" / "raw"
    raw = raw_dir / f"research_eur_usd_{start}_{end}_ecb.csv"
    meta = raw.with_suffix(".metadata.json")
    if offline and (not raw.is_file() or not meta.is_file()):
        raise ValueError(f"Offline mode needs both snapshot files: {raw.name}")
    if not offline:
        raw, meta = download_snapshot(start, end, raw_dir)
    quotes = load_snapshot(raw, meta)
    audit = audit_quotes(quotes, start, end)
    if not audit["passed_all_checks"]:
        raise ValueError(f"Publication-calendar audit failed: {audit}")
    return quotes, {"raw_file": raw.relative_to(ROOT).as_posix(),
                    "metadata_file": meta.relative_to(ROOT).as_posix(),
                    "raw_sha256": sha256(raw), "metadata_sha256": sha256(meta), "audit": audit}


def split_name(target_date, config):
    if not config["start_date"] <= target_date <= config["end_date"]:
        raise ValueError("Target outside study period.")
    if target_date <= config["development_end"]:
        return "development"
    if target_date <= config["validation_end"]:
        return "validation"
    return "final"


def summarize(forecasts):
    result = mse_comparison(forecasts)
    return {"first_target_date": forecasts[0]["date"], "last_target_date": forecasts[-1]["date"], **result}


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_figures(forecasts, annual, output_dir, stage, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = list(annual)
    xs = list(range(len(years)))
    rolling_label = f"Rolling {config['rolling_window']}"
    ewma_label = f"EWMA {config['ewma_decay']:g}"
    fig, ax = plt.subplots(figsize=(11, 4.8), layout="constrained")
    ax.bar([x - .2 for x in xs], [annual[y]["rolling_mse"] for y in years], .4, label=rolling_label, color="#264b70")
    ax.bar([x + .2 for x in xs], [annual[y]["ewma_mse"] for y in years], .4, label=ewma_label, color="#15847b")
    ax.set_xticks(xs, years, rotation=45)
    ax.set(title="Forecast error by target year", ylabel="MSE of squared decimal returns (return⁴)")
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output_dir / f"{stage}_annual_mse.png", dpi=150)
    plt.close(fig)

    # Readable display only: monthly averages are not used to score forecasts.
    shown = [row for row in forecasts if row["split"] == ("final" if stage == "final" else "validation")]
    monthly = defaultdict(list)
    for row in shown:
        monthly[row["date"][:7]].append(row)
    fig, ax = plt.subplots(figsize=(11, 4.8), layout="constrained")
    dates = [date.fromisoformat(month + "-01") for month in monthly]
    for key, label, color in (("target_squared_return", "Observed squared return", "#8a8790"),
                              ("rolling_forecast", rolling_label, "#264b70"),
                              ("ewma_forecast", ewma_label, "#15847b")):
        values = [sum(r[key] for r in rows) / len(rows) for rows in monthly.values()]
        ax.plot(dates, values, label=label, color=color, linewidth=1.6, marker="o", markersize=3)
    period = (f"Final {config['final_start']} to {config['end_date']}" if stage == "final"
              else f"Validation {config['validation_start']} to {config['validation_end']}")
    ax.set(title=f"{period}: monthly averages for display",
           ylabel="Squared decimal return / forecast (return²)", xlabel="Target month; scores use individual intervals")
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output_dir / f"{stage}_forecast_comparison.png", dpi=150)
    plt.close(fig)


def run(stage="development", offline=False, freeze=False):
    config = read_config()
    # This check happens before any access to the final-period file or endpoint.
    lock = require_lock() if stage == "final" else None
    if freeze and stage != "development":
        raise ValueError("Freeze the development run before final evaluation.")
    if freeze and LOCK_PATH.exists():
        require_lock()  # existing locks cannot be silently replaced
    quotes, source = snapshot(config["start_date"], config["validation_end"], offline)
    sources = [source]
    if stage == "final":
        if source["raw_sha256"] != lock["development_snapshot_sha256"]:
            raise ValueError("Development data changed after protocol freeze.")
        final_quotes, final_source = snapshot(config["final_start"], config["end_date"], offline)
        quotes += final_quotes
        sources.append(final_source)
    audit_end = config["end_date"] if stage == "final" else config["validation_end"]
    combined_audit = audit_quotes(quotes, config["start_date"], audit_end)
    if not combined_audit["passed_all_checks"]:
        raise ValueError("Combined quote audit failed.")
    returns = make_interval_returns(quotes)
    forecasts = forecast_returns(returns, window=config["rolling_window"], decay=config["ewma_decay"])
    for row in forecasts:
        row["split"] = split_name(row["date"], config)
    by_split, by_year, by_gap = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in forecasts:
        by_split[row["split"]].append(row)
        by_year[row["date"][:4]].append(row)
        by_gap[f"{row['split']}:{row['calendar_gap_days']}_calendar_days"].append(row)
    summary = {"study_id": config["study_id"], "stage": stage,
               "quote_count": len(quotes), "return_count": len(returns),
               "warmup_return_count": config["rolling_window"], "forecast_count": len(forecasts),
               "config": config, "sources": sources, "combined_audit": combined_audit,
               "scores_by_split": {k: summarize(v) for k, v in by_split.items()},
               "scores_by_target_year": {k: summarize(v) for k, v in by_year.items()},
               "scores_by_split_and_gap": {k: summarize(v) for k, v in by_gap.items()},
               "runtime": {"python": platform.python_version()},
               "file_sha256": code_fingerprints(),
               "interpretation": "negative relative MSE change means lower EWMA error; descriptive only"}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    save_csv(ROOT / "data" / "processed" / f"research_{stage}_quotes.csv", quotes)
    save_csv(REPORT_DIR / f"{stage}_forecasts.csv", forecasts)
    save_figures(forecasts, summary["scores_by_target_year"], REPORT_DIR, stage, config)
    import matplotlib
    summary["runtime"]["matplotlib"] = matplotlib.__version__
    write_json(REPORT_DIR / f"{stage}_summary.json", summary)
    if freeze and not LOCK_PATH.exists():
        write_json(LOCK_PATH, {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "Local protocol record created before this pipeline's first final-period access; not an external preregistration.",
            "file_sha256": code_fingerprints(),
            "development_snapshot_sha256": source["raw_sha256"],
            "development_summary_sha256": sha256(REPORT_DIR / "development_summary.json"),
            "final_data_accessed_by_this_pipeline_before_lock": False,
        })
    print(f"{stage}: {len(quotes)} quotes, {len(forecasts)} forecasts; audit passed")
    for name, scores in summary["scores_by_split"].items():
        relative = scores["ewma_relative_mse_change"]
        text = "undefined" if relative is None else f"{relative:+.2%}"
        print(f"  {name}: n={scores['count']}; EWMA/rolling MSE - 1 = {text}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "final"), default="development")
    parser.add_argument("--offline", action="store_true", help="Require preserved local snapshots; never use the network")
    parser.add_argument("--freeze", action="store_true", help="Write an immutable local protocol record after development")
    args = parser.parse_args()
    try:
        run(args.stage, args.offline, args.freeze)
    except (ValueError, OSError, KeyError) as error:
        print(f"Research stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
