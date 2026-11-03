"""Day 3: retrieve and inspect a small ECB EUR/USD reference-rate dataset.

Run with Python 3. No third-party packages are needed.
The series is quoted in US dollars per euro, not euros per US dollar.
"""

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# A fixed month is enough to learn the data format before expanding the study.
START_DATE = "2024-01-01"
END_DATE = "2024-01-31"
SERIES_KEY = "D.USD.EUR.SP00.A"
URL = (
    f"https://data-api.ecb.europa.eu/service/data/EXR/{SERIES_KEY}"
    f"?startPeriod={START_DATE}&endPeriod={END_DATE}&format=csvdata"
)

# Anchor paths to this file, so running it from another folder still works.
PROJECT_DIR = Path(__file__).resolve().parent
FILE_STEM = f"eur_usd_{START_DATE}_{END_DATE}"
RAW_FILE = PROJECT_DIR / "data" / "raw" / f"{FILE_STEM}_ecb.csv"
METADATA_FILE = RAW_FILE.with_suffix(".metadata.json")
PROCESSED_FILE = PROJECT_DIR / "data" / "processed" / f"{FILE_STEM}.csv"


def parse_observations(payload):
    """Read rows by column name and extract date and USD-per-EUR rate."""
    csv_text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))
    required_columns = {"TIME_PERIOD", "OBS_VALUE", "CURRENCY", "CURRENCY_DENOM"}

    if not required_columns.issubset(reader.fieldnames or []):
        raise ValueError("The response does not contain the expected ECB CSV columns.")

    observations = []
    seen_dates = set()

    for row in reader:
        if row["CURRENCY"] != "USD" or row["CURRENCY_DENOM"] != "EUR":
            raise ValueError("An unexpected currency pair was returned.")

        observation_date = date.fromisoformat(row["TIME_PERIOD"])
        if not START_DATE <= observation_date.isoformat() <= END_DATE:
            raise ValueError("An observation lies outside the requested date range.")
        if observation_date in seen_dates:
            raise ValueError(f"Duplicate observation date: {observation_date}")

        rate = float(row["OBS_VALUE"])
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"Invalid exchange rate on {observation_date}")

        seen_dates.add(observation_date)
        observations.append({"date": observation_date.isoformat(), "usd_per_eur": rate})

    if not observations:
        raise ValueError("No observations were returned for this date range.")

    return sorted(observations, key=lambda observation: observation["date"])


def get_snapshot():
    """Download once, then reuse the saved original response and its metadata."""
    if RAW_FILE.exists() or METADATA_FILE.exists():
        if not (RAW_FILE.exists() and METADATA_FILE.exists()):
            raise ValueError("The saved snapshot is incomplete: CSV and metadata are both needed.")

        payload = RAW_FILE.read_bytes()
        metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        if metadata["request_url"] != URL:
            raise ValueError("The saved snapshot belongs to a different request.")
        if hashlib.sha256(payload).hexdigest() != metadata["raw_sha256"]:
            raise ValueError("The saved original CSV has changed since its retrieval.")

        print("Using the saved snapshot; no new download is needed.")
        return payload

    request = Request(URL, headers={"Accept": "text/csv"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()

    # Reject an invalid response before saving it as research data.
    observations = parse_observations(payload)
    metadata = {
        "source": "European Central Bank",
        "source_documentation": "https://data.ecb.europa.eu/help/api/data-examples",
        "request_url": URL,
        "series_key": f"EXR.{SERIES_KEY}",
        "requested_start_date": START_DATE,
        "requested_end_date": END_DATE,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "quote_units": "US dollars per one euro",
        "rate_type": "Daily reference rate; not an executable price or market close",
        "raw_sha256": hashlib.sha256(payload).hexdigest(),
        "observation_count": len(observations),
        "first_observation_date": observations[0]["date"],
        "last_observation_date": observations[-1]["date"],
    }

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_bytes(payload)
    METADATA_FILE.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print("Downloaded a new snapshot from the ECB.")
    return payload


def main():
    observations = parse_observations(get_snapshot())

    # The simplified file is reproducible from the original snapshot.
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROCESSED_FILE.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["date", "usd_per_eur"])
        writer.writeheader()
        writer.writerows(observations)

    print(f"Series: EXR.{SERIES_KEY}")
    print("Units: US dollars per one euro")
    print(f"Observations: {len(observations)}")
    print(f"First observation: {observations[0]['date']}")
    print(f"Last observation: {observations[-1]['date']}")
    print("\nFirst five observations:")
    for observation in observations[:5]:
        print(f"{observation['date']}: 1 EUR = {observation['usd_per_eur']:.4f} USD")

    print(f"\nOriginal CSV: {RAW_FILE}")
    print(f"Retrieval metadata: {METADATA_FILE}")
    print(f"Working CSV: {PROCESSED_FILE}")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Data download or reading failed: {error}") from error
