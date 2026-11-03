"""Immutable ECB EUR/USD snapshots and publication-calendar checks.

This module belongs to the separate research study.  It does not change or
import the Day 1--6 learning exercises.  Importing it never downloads data.
All rates are US dollars per one euro.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen


SERIES_KEY = "EXR.D.USD.EUR.SP00.A"
API_BASE_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
CALENDAR_FIRST_YEAR = 2010
CALENDAR_LAST_YEAR = 2025
_REQUIRED_COLUMNS = {
    "KEY", "FREQ", "CURRENCY", "CURRENCY_DENOM", "EXR_TYPE", "EXR_SUFFIX",
    "TIME_PERIOD", "OBS_VALUE", "UNIT", "UNIT_MULT",
}
_SERIES_DIMENSIONS = {
    "KEY": SERIES_KEY,
    "FREQ": "D",
    "CURRENCY": "USD",
    "CURRENCY_DENOM": "EUR",
    "EXR_TYPE": "SP00",
    "EXR_SUFFIX": "A",
    "UNIT": "USD",
    "UNIT_MULT": "0",
}


def _iso_date(value: str, label: str) -> date:
    """Require the canonical YYYY-MM-DD representation, not ISO shortcuts."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string (YYYY-MM-DD).")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid {label}: {value!r}.") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must use YYYY-MM-DD: {value!r}.")
    return parsed


def _date_range(start_date: str, end_date: str) -> tuple[date, date]:
    start = _iso_date(start_date, "start_date")
    end = _iso_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must be on or before end_date.")
    return start, end


def _request_url(start_date: str, end_date: str) -> str:
    _date_range(start_date, end_date)
    return (
        f"{API_BASE_URL}?startPeriod={start_date}"
        f"&endPeriod={end_date}&format=csvdata"
    )


def parse_ecb_csv(
    payload: bytes, start_date: str, end_date: str,
) -> list[dict[str, Any]]:
    """Validate an original ECB response and return sorted daily quotes.

    Additional ECB descriptive columns are allowed.  Every raw row must
    belong to the exact unscaled daily reference-rate series requested here.
    An empty value explicitly marked H (holiday/weekend) is retained in the
    original snapshot but omitted from quotes after checking the calendar.
    """
    start, end = _date_range(start_date, end_date)
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("The ECB CSV response must contain nonempty bytes.")
    try:
        csv_text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("The ECB CSV response is not valid UTF-8.") from error

    reader = csv.DictReader(io.StringIO(csv_text, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames or []
        if not _REQUIRED_COLUMNS.issubset(fieldnames):
            missing = sorted(_REQUIRED_COLUMNS - set(fieldnames))
            raise ValueError(f"Required ECB CSV columns are missing: {missing}.")
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("The ECB CSV contains duplicate column names.")

        quotes = []
        seen_dates = set()
        for row in reader:
            if None in row:
                raise ValueError(f"Malformed ECB CSV row at line {reader.line_num}.")
            for column, expected in _SERIES_DIMENSIONS.items():
                if row[column] != expected:
                    raise ValueError(
                        f"Unexpected {column} at line {reader.line_num}: "
                        f"{row[column]!r}; expected {expected!r}."
                    )

            observation_date = _iso_date(row["TIME_PERIOD"], "observation date")
            if not start <= observation_date <= end:
                raise ValueError(
                    f"Observation {observation_date.isoformat()} is outside "
                    "the requested date range."
                )
            if observation_date in seen_dates:
                raise ValueError(f"Duplicate observation date: {observation_date}.")
            seen_dates.add(observation_date)

            raw_rate = row["OBS_VALUE"]
            if row.get("OBS_STATUS") == "H":
                if raw_rate != "":
                    raise ValueError(
                        f"Holiday placeholder on {observation_date} has a value."
                    )
                observation_iso = observation_date.isoformat()
                if observation_iso in expected_publication_dates(observation_iso, observation_iso):
                    raise ValueError(
                        f"Holiday placeholder on {observation_date} falls on an "
                        "expected publication date."
                    )
                continue
            try:
                rate = float(raw_rate)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid exchange rate on {observation_date}."
                ) from error
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(f"Invalid exchange rate on {observation_date}.")

            quotes.append({"date": observation_date.isoformat(), "usd_per_eur": rate})
    except csv.Error as error:
        raise ValueError(f"Malformed ECB CSV: {error}.") from error

    if not quotes:
        raise ValueError("The ECB CSV contains no observations.")
    return sorted(quotes, key=lambda quote: quote["date"])


def _read_snapshot(
    raw_path: Path, metadata_path: Path, expected_url: str | None = None,
) -> list[dict[str, Any]]:
    if not raw_path.is_file() or not metadata_path.is_file():
        raise ValueError("A snapshot requires both the original CSV and its metadata.")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Snapshot metadata must be a valid UTF-8 JSON object.") from error
    if not isinstance(metadata, dict):
        raise ValueError("Snapshot metadata must be a JSON object.")
    required = {"requested_start_date", "requested_end_date", "request_url", "raw_sha256"}
    if not required.issubset(metadata):
        raise ValueError("Snapshot metadata is missing request or integrity fields.")

    start_date = metadata["requested_start_date"]
    end_date = metadata["requested_end_date"]
    canonical_url = _request_url(start_date, end_date)
    if metadata["request_url"] != canonical_url:
        raise ValueError("Snapshot metadata contains an inconsistent request URL.")
    if expected_url is not None and metadata["request_url"] != expected_url:
        raise ValueError("The cached snapshot belongs to a different request.")
    if "series_key" in metadata and metadata["series_key"] != SERIES_KEY:
        raise ValueError("The snapshot metadata identifies a different ECB series.")

    payload = raw_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["raw_sha256"]:
        raise ValueError("The original CSV does not match its saved SHA-256 hash.")
    return parse_ecb_csv(payload, start_date, end_date)


def load_snapshot(raw_path: Path, metadata_path: Path) -> list[dict[str, Any]]:
    """Verify a saved request and original-byte hash, then parse its quotes."""
    return _read_snapshot(Path(raw_path), Path(metadata_path))


def download_snapshot(
    start_date: str, end_date: str, output_dir: Path,
) -> tuple[Path, Path]:
    """Reuse a verified snapshot or save a new validated response exclusively.

    HTTPS uses Python's default certificate verification.  Existing snapshot
    files are never overwritten, including incomplete or invalid snapshots.
    """
    request_url = _request_url(start_date, end_date)
    output_dir = Path(output_dir)
    stem = f"research_eur_usd_{start_date}_{end_date}_ecb"
    raw_path = output_dir / f"{stem}.csv"
    metadata_path = output_dir / f"{stem}.metadata.json"

    if raw_path.exists() or metadata_path.exists():
        _read_snapshot(raw_path, metadata_path, expected_url=request_url)
        return raw_path, metadata_path

    request = Request(request_url, headers={"Accept": "text/csv"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
    retrieved_at_utc = datetime.now(timezone.utc).isoformat()
    quotes = parse_ecb_csv(payload, start_date, end_date)
    raw_rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True))
    holiday_placeholder_dates = sorted(
        row["TIME_PERIOD"] for row in raw_rows
        if row.get("OBS_STATUS") == "H" and row["OBS_VALUE"] == ""
    )
    metadata = {
        "source": "European Central Bank",
        "source_documentation": "https://data.ecb.europa.eu/help/api/data-examples",
        "request_url": request_url,
        "series_key": SERIES_KEY,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "retrieved_at_utc": retrieved_at_utc,
        "quote_units": "US dollars per one euro",
        "rate_type": "Daily reference rate; not an executable price or market close",
        "raw_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_row_count": len(raw_rows),
        "skipped_holiday_placeholder_count": len(holiday_placeholder_dates),
        "skipped_holiday_placeholder_dates": holiday_placeholder_dates,
        "observation_count": len(quotes),
        "first_observation_date": quotes[0]["date"],
        "last_observation_date": quotes[-1]["date"],
    }
    metadata_text = json.dumps(metadata, indent=2, allow_nan=False) + "\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    # Exclusive modes enforce immutability even if another process creates a
    # snapshot between the initial cache check and these writes.
    created_raw = False
    created_metadata = False
    try:
        with raw_path.open("xb") as raw_file:
            created_raw = True
            with metadata_path.open("x", encoding="utf-8", newline="\n") as metadata_file:
                created_metadata = True
                raw_file.write(payload)
                metadata_file.write(metadata_text)
    except BaseException:
        # Remove only files created by this unsuccessful attempt.  Previously
        # existing files are never opened for writing or removed.
        if created_metadata:
            metadata_path.unlink(missing_ok=True)
        if created_raw:
            raw_path.unlink(missing_ok=True)
        raise
    return raw_path, metadata_path


def _gregorian_easter(year: int) -> date:
    """Return Gregorian Easter Sunday using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day_zero = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day_zero + 1)


def expected_publication_dates(start_date: str, end_date: str) -> set[str]:
    """Return ECB publication weekdays for the study's 2010--2025 calendar.

    TARGET closing days in this period are New Year's Day, Good Friday,
    Easter Monday, 1 May, Christmas Day, and 26 December.  Weekend holidays
    do not create replacement closing days on adjacent weekdays.
    """
    start, end = _date_range(start_date, end_date)
    if start.year < CALENDAR_FIRST_YEAR or end.year > CALENDAR_LAST_YEAR:
        raise ValueError(
            f"The verified publication calendar supports {CALENDAR_FIRST_YEAR}"
            f"--{CALENDAR_LAST_YEAR} only."
        )
    closed_dates = set()
    for year in range(start.year, end.year + 1):
        easter = _gregorian_easter(year)
        closed_dates.update({
            date(year, 1, 1), easter - timedelta(days=2),
            easter + timedelta(days=1), date(year, 5, 1),
            date(year, 12, 25), date(year, 12, 26),
        })
    expected = set()
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in closed_dates:
            expected.add(current.isoformat())
        current += timedelta(days=1)
    return expected


def audit_quotes(
    quotes: Iterable[Mapping[str, Any]], start_date: str, end_date: str,
) -> dict[str, Any]:
    """Report quote validity and exact publication-calendar completeness.

    Invalid quote rows fail checks in the report.  Invalid requested bounds
    and dates outside the supported calendar raise ValueError.
    """
    start, end = _date_range(start_date, end_date)
    expected = expected_publication_dates(start_date, end_date)
    rows = list(quotes)
    valid_dates = []
    valid_rates = True
    for row in rows:
        try:
            valid_dates.append(_iso_date(row["date"], "quote date"))
        except (KeyError, TypeError, ValueError):
            pass
        try:
            raw_rate = row["usd_per_eur"]
            rate = float(raw_rate)
            valid_rates = valid_rates and not isinstance(raw_rate, bool) and (
                math.isfinite(rate) and rate > 0
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            valid_rates = False

    all_dates_valid = len(valid_dates) == len(rows)
    observed = {day.isoformat() for day in valid_dates}
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    checks = {
        "nonempty": bool(rows),
        "valid_iso_dates": all_dates_valid,
        "unique_dates": all_dates_valid and len(valid_dates) == len(observed),
        "chronological_order": all_dates_valid and all(
            previous < current
            for previous, current in zip(valid_dates, valid_dates[1:])
        ),
        "positive_finite_rates": valid_rates,
        "within_requested_range": all_dates_valid and all(
            start <= day <= end for day in valid_dates
        ),
        "complete_publication_calendar": not missing,
        "no_unexpected_dates": not unexpected,
    }
    source_start = min(observed) if observed else None
    source_end = max(observed) if observed else None
    return {
        "series_key": SERIES_KEY,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "source_start_date": source_start,
        "source_end_date": source_end,
        "first_observation_date": source_start,
        "last_observation_date": source_end,
        "expected_count": len(expected),
        "observed_count": len(rows),
        "checks": checks,
        "missing_expected_dates": missing,
        "unexpected_dates": unexpected,
        "passed_all_checks": all(checks.values()),
    }
