"""Offline source validation, immutable snapshot, and calendar regression tests.

No test performs an HTTP request.  Calendar fixtures use Gregorian Easter
dates for each study year and the ECB's six TARGET holiday closures.
"""

import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import research_data


START = "2024-01-01"
END = "2024-01-31"
REQUEST_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    "?startPeriod=2024-01-01&endPeriod=2024-01-31&format=csvdata"
)
CSV_COLUMNS = [
    "KEY", "FREQ", "CURRENCY", "CURRENCY_DENOM", "EXR_TYPE", "EXR_SUFFIX",
    "TIME_PERIOD", "OBS_VALUE", "UNIT", "UNIT_MULT",
]
BASE_ROW = {
    "KEY": "EXR.D.USD.EUR.SP00.A", "FREQ": "D", "CURRENCY": "USD",
    "CURRENCY_DENOM": "EUR", "EXR_TYPE": "SP00", "EXR_SUFFIX": "A",
    "TIME_PERIOD": "2024-01-02", "OBS_VALUE": "1.0956", "UNIT": "USD",
    "UNIT_MULT": "0",
}
SECOND_ROW = dict(BASE_ROW, TIME_PERIOD="2024-01-03", OBS_VALUE="1.0919")
QUOTES = [
    {"date": "2024-01-02", "usd_per_eur": 1.0956},
    {"date": "2024-01-03", "usd_per_eur": 1.0919},
]


def csv_payload(rows, columns=CSV_COLUMNS):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class ParserTests(unittest.TestCase):
    def test_sorts_dates_and_accepts_utf8_bom_and_descriptive_columns(self):
        rows = [dict(SECOND_ROW, TITLE="ECB reference rate"), dict(BASE_ROW, TITLE="ECB reference rate")]
        raw = b"\xef\xbb\xbf" + csv_payload(rows, CSV_COLUMNS + ["TITLE"])
        self.assertEqual(research_data.parse_ecb_csv(raw, START, END), QUOTES)

    def test_each_series_dimension_must_match_the_exact_unscaled_series(self):
        bad_dimensions = {
            "KEY": "EXR.M.USD.EUR.SP00.A", "FREQ": "M", "CURRENCY": "GBP",
            "CURRENCY_DENOM": "USD", "EXR_TYPE": "OTHER", "EXR_SUFFIX": "E",
            "UNIT": "EUR", "UNIT_MULT": "3",
        }
        for column, value in bad_dimensions.items():
            with self.subTest(column=column), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(csv_payload([dict(BASE_ROW, **{column: value})]), START, END)

    def test_missing_duplicate_and_malformed_columns_are_rejected(self):
        invalid = [
            b"KEY,TIME_PERIOD,OBS_VALUE\n",
            csv_payload([BASE_ROW]).replace(b"KEY,FREQ", b"KEY,KEY"),
            csv_payload([BASE_ROW]) + b"bad,extra,fields\n",
            csv_payload([BASE_ROW]).replace(b"1.0956", b'"unterminated'),
        ]
        for raw in invalid:
            with self.subTest(payload=raw), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(raw, START, END)

    def test_empty_and_non_utf8_responses_are_rejected(self):
        for raw in (b"", csv_payload([]), b"\xff\xfe"):
            with self.subTest(payload=raw), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(raw, START, END)

    def test_nonpositive_nonfinite_missing_and_nonnumeric_rates_are_rejected(self):
        for value in ("", "nan", "inf", "-inf", "0", "-1", "not a number"):
            with self.subTest(rate=value), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(csv_payload([dict(BASE_ROW, OBS_VALUE=value)]), START, END)

    def test_noncanonical_impossible_and_outside_dates_are_rejected(self):
        for value in ("", "20240102", "2024-W01-2", "2024-02-30", "2023-12-29", "2024-02-01"):
            with self.subTest(date=value), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(csv_payload([dict(BASE_ROW, TIME_PERIOD=value)]), START, END)

    def test_duplicate_observations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            research_data.parse_ecb_csv(csv_payload([BASE_ROW, BASE_ROW]), START, END)

    def test_invalid_requested_bounds_are_rejected(self):
        for start, end in ((END, START), ("20240101", END), (START, "2024-02-30")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(csv_payload([BASE_ROW]), start, end)

    def test_only_explicit_calendar_holiday_placeholders_are_omitted(self):
        # Nine H rows occur in the inspected 2010--2024 original ECB response.
        holiday_dates = [
            "2010-01-01", "2010-04-02", "2010-04-05", "2011-04-22", "2011-04-25",
            "2011-12-26", "2012-04-06", "2012-04-09", "2012-05-01",
        ]
        placeholders = [
            dict(BASE_ROW, TIME_PERIOD=day, OBS_VALUE="", OBS_STATUS="H")
            for day in holiday_dates
        ]
        numeric = dict(BASE_ROW, TIME_PERIOD="2012-05-02", OBS_STATUS="A")
        raw = csv_payload(placeholders + [numeric], CSV_COLUMNS + ["OBS_STATUS"])
        self.assertEqual(
            research_data.parse_ecb_csv(raw, "2010-01-01", "2012-05-02"),
            [{"date": "2012-05-02", "usd_per_eur": 1.0956}],
        )

    def test_explicit_weekend_placeholder_can_be_omitted(self):
        rows = [
            dict(BASE_ROW, TIME_PERIOD="2024-01-06", OBS_VALUE="", OBS_STATUS="H"),
            dict(BASE_ROW, TIME_PERIOD="2024-01-08", OBS_STATUS="A"),
        ]
        self.assertEqual(
            research_data.parse_ecb_csv(csv_payload(rows, CSV_COLUMNS + ["OBS_STATUS"]), START, END),
            [{"date": "2024-01-08", "usd_per_eur": 1.0956}],
        )

    def test_blank_normal_missing_or_unmarked_values_are_rejected(self):
        for status in ("A", "M", ""):
            with self.subTest(status=status), self.assertRaises(ValueError):
                raw = csv_payload([dict(BASE_ROW, OBS_VALUE="", OBS_STATUS=status)], CSV_COLUMNS + ["OBS_STATUS"])
                research_data.parse_ecb_csv(raw, START, END)

    def test_holiday_marker_on_publication_day_or_with_a_value_is_rejected(self):
        bad_rows = [
            dict(BASE_ROW, OBS_VALUE="", OBS_STATUS="H"),
            dict(BASE_ROW, TIME_PERIOD="2024-01-01", OBS_STATUS="H"),
            dict(BASE_ROW, TIME_PERIOD="2024-01-01", OBS_VALUE="nan", OBS_STATUS="H"),
        ]
        for row in bad_rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                research_data.parse_ecb_csv(csv_payload([row], CSV_COLUMNS + ["OBS_STATUS"]), START, END)

    def test_skipped_placeholder_dates_still_participate_in_duplicate_checks(self):
        holiday = dict(BASE_ROW, TIME_PERIOD="2024-01-01", OBS_VALUE="", OBS_STATUS="H")
        numeric = dict(SECOND_ROW, OBS_STATUS="A")
        raw = csv_payload([holiday, holiday, numeric], CSV_COLUMNS + ["OBS_STATUS"])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            research_data.parse_ecb_csv(raw, START, END)

    def test_a_response_containing_only_holiday_placeholders_is_still_empty(self):
        holiday = dict(BASE_ROW, TIME_PERIOD="2024-01-01", OBS_VALUE="", OBS_STATUS="H")
        with self.assertRaisesRegex(ValueError, "no observations"):
            research_data.parse_ecb_csv(csv_payload([holiday], CSV_COLUMNS + ["OBS_STATUS"]), START, END)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.raw_path = self.directory / "research_eur_usd_2024-01-01_2024-01-31_ecb.csv"
        self.metadata_path = self.raw_path.with_suffix(".metadata.json")
        self.payload = csv_payload([SECOND_ROW, BASE_ROW])
        no_network = patch.object(
            research_data, "urlopen", side_effect=AssertionError("Unexpected HTTP request in offline test")
        )
        self.urlopen = no_network.start()
        self.addCleanup(no_network.stop)

    def download_fixture(self):
        self.urlopen.side_effect = lambda request, timeout: io.BytesIO(self.payload)
        result = research_data.download_snapshot(START, END, self.directory)
        self.urlopen.side_effect = AssertionError("Cached data must not cause an HTTP request")
        self.urlopen.reset_mock()
        return result

    def read_metadata(self):
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def write_metadata(self, metadata):
        self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    def test_download_retains_original_bytes_request_hash_and_utc_timestamp(self):
        self.urlopen.side_effect = lambda request, timeout: io.BytesIO(self.payload)
        before = datetime.now(timezone.utc)
        paths = research_data.download_snapshot(START, END, self.directory)
        after = datetime.now(timezone.utc)
        self.assertEqual(paths, (self.raw_path, self.metadata_path))
        self.assertEqual(self.raw_path.read_bytes(), self.payload)
        self.urlopen.assert_called_once()
        request = self.urlopen.call_args.args[0]
        self.assertEqual(request.full_url, REQUEST_URL)
        self.assertEqual(request.get_header("Accept"), "text/csv")
        # Omitting a custom context preserves urlopen's default HTTPS verification.
        self.assertEqual(self.urlopen.call_args.kwargs, {"timeout": 30})
        metadata = self.read_metadata()
        self.assertEqual(metadata["request_url"], REQUEST_URL)
        self.assertEqual(metadata["series_key"], "EXR.D.USD.EUR.SP00.A")
        self.assertEqual(metadata["raw_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(metadata["requested_start_date"], START)
        self.assertEqual(metadata["requested_end_date"], END)
        self.assertEqual(metadata["raw_row_count"], 2)
        self.assertEqual(metadata["skipped_holiday_placeholder_count"], 0)
        self.assertEqual(metadata["skipped_holiday_placeholder_dates"], [])
        retrieved = datetime.fromisoformat(metadata["retrieved_at_utc"])
        self.assertEqual(retrieved.utcoffset(), timedelta(0))
        self.assertLessEqual(before, retrieved)
        self.assertLessEqual(retrieved, after)
        self.assertEqual(research_data.load_snapshot(*paths), QUOTES)

    def test_holiday_placeholder_bytes_and_provenance_are_retained(self):
        holiday = dict(BASE_ROW, TIME_PERIOD="2024-01-01", OBS_VALUE="", OBS_STATUS="H")
        numeric = [dict(row, OBS_STATUS="A") for row in (BASE_ROW, SECOND_ROW)]
        self.payload = csv_payload([holiday] + numeric, CSV_COLUMNS + ["OBS_STATUS"])
        paths = self.download_fixture()
        self.assertEqual(self.raw_path.read_bytes(), self.payload)
        metadata = self.read_metadata()
        self.assertEqual(metadata["raw_row_count"], 3)
        self.assertEqual(metadata["skipped_holiday_placeholder_count"], 1)
        self.assertEqual(metadata["skipped_holiday_placeholder_dates"], ["2024-01-01"])
        self.assertEqual(metadata["observation_count"], 2)
        self.assertEqual(research_data.load_snapshot(*paths), QUOTES)

    def test_cache_reuses_both_files_without_rewriting_or_requesting_http(self):
        self.download_fixture()
        before = [
            (path.read_bytes(), path.stat().st_mtime_ns)
            for path in (self.raw_path, self.metadata_path)
        ]
        self.assertEqual(
            research_data.download_snapshot(START, END, self.directory),
            (self.raw_path, self.metadata_path),
        )
        after = [
            (path.read_bytes(), path.stat().st_mtime_ns)
            for path in (self.raw_path, self.metadata_path)
        ]
        self.assertEqual(before, after)
        self.urlopen.assert_not_called()

    def test_corrupted_raw_bytes_fail_integrity_without_overwrite_or_http(self):
        self.download_fixture()
        altered = self.payload + b"\n"
        self.raw_path.write_bytes(altered)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            research_data.download_snapshot(START, END, self.directory)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            research_data.load_snapshot(self.raw_path, self.metadata_path)
        self.assertEqual(self.raw_path.read_bytes(), altered)
        self.urlopen.assert_not_called()

    def test_changed_request_url_and_series_are_rejected(self):
        self.download_fixture()
        original = self.read_metadata()
        for changes in (
            {"request_url": REQUEST_URL + "&changed=1"},
            {"series_key": "EXR.D.GBP.EUR.SP00.A"},
        ):
            with self.subTest(changes=changes):
                self.write_metadata(dict(original, **changes))
                with self.assertRaises(ValueError):
                    research_data.load_snapshot(self.raw_path, self.metadata_path)
        self.urlopen.assert_not_called()

    def test_canonical_request_for_different_bounds_cannot_reuse_cached_filename(self):
        self.download_fixture()
        metadata = self.read_metadata()
        metadata["requested_end_date"] = "2024-01-30"
        metadata["request_url"] = REQUEST_URL.replace("endPeriod=2024-01-31", "endPeriod=2024-01-30")
        self.write_metadata(metadata)
        with self.assertRaisesRegex(ValueError, "different request"):
            research_data.download_snapshot(START, END, self.directory)
        self.urlopen.assert_not_called()

    def test_incomplete_snapshot_never_downloads_or_overwrites_remaining_file(self):
        for remaining in (self.raw_path, self.metadata_path):
            with self.subTest(remaining=remaining.name):
                remaining.write_bytes(b"retain existing file")
                with self.assertRaisesRegex(ValueError, "both"):
                    research_data.download_snapshot(START, END, self.directory)
                self.assertEqual(remaining.read_bytes(), b"retain existing file")
                remaining.unlink()
        self.urlopen.assert_not_called()

    def test_invalid_download_is_rejected_before_any_snapshot_file_is_written(self):
        self.urlopen.side_effect = lambda request, timeout: io.BytesIO(csv_payload([]))
        with self.assertRaises(ValueError):
            research_data.download_snapshot(START, END, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_file_appearing_after_cache_check_is_never_overwritten(self):
        for existing in (self.raw_path, self.metadata_path):
            with self.subTest(existing=existing.name):
                def respond(request, timeout):
                    existing.write_bytes(b"another process owns this snapshot")
                    return io.BytesIO(self.payload)

                self.urlopen.side_effect = respond
                with self.assertRaises(FileExistsError):
                    research_data.download_snapshot(START, END, self.directory)
                self.assertEqual(existing.read_bytes(), b"another process owns this snapshot")
                other = self.metadata_path if existing == self.raw_path else self.raw_path
                self.assertFalse(other.exists())
                existing.unlink()

    def test_invalid_metadata_objects_are_rejected(self):
        self.download_fixture()
        for value in ("not JSON", "[]", "{}", '{"raw_sha256": "missing request fields"}'):
            with self.subTest(metadata=value):
                self.metadata_path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    research_data.load_snapshot(self.raw_path, self.metadata_path)


class PublicationCalendarTests(unittest.TestCase):
    # Hard-coded dates make these tests independent of the production Easter algorithm.
    EASTER_SUNDAYS = {
        2010: "2010-04-04", 2011: "2011-04-24", 2012: "2012-04-08", 2013: "2013-03-31",
        2014: "2014-04-20", 2015: "2015-04-05", 2016: "2016-03-27", 2017: "2017-04-16",
        2018: "2018-04-01", 2019: "2019-04-21", 2020: "2020-04-12", 2021: "2021-04-04",
        2022: "2022-04-17", 2023: "2023-04-09", 2024: "2024-03-31", 2025: "2025-04-20",
    }

    def test_easter_closures_for_every_supported_year(self):
        for year, easter_string in self.EASTER_SUNDAYS.items():
            with self.subTest(year=year):
                easter = date.fromisoformat(easter_string)
                thursday = (easter - timedelta(days=3)).isoformat()
                tuesday = (easter + timedelta(days=2)).isoformat()
                self.assertEqual(
                    research_data.expected_publication_dates(thursday, tuesday),
                    {thursday, tuesday},
                )

    def test_all_supported_years_exclude_fixed_holidays_and_weekends(self):
        for year in range(2010, 2026):
            with self.subTest(year=year):
                expected = research_data.expected_publication_dates(f"{year}-01-01", f"{year}-12-31")
                for holiday in ("01-01", "05-01", "12-25", "12-26"):
                    self.assertNotIn(f"{year}-{holiday}", expected)
                self.assertTrue(all(date.fromisoformat(day).weekday() < 5 for day in expected))

    def test_weekend_holidays_do_not_close_the_following_monday(self):
        cases = [
            ("2011-01-01", "2011-01-03", {"2011-01-03"}),
            ("2012-01-01", "2012-01-02", {"2012-01-02"}),
            ("2021-12-24", "2021-12-28", {"2021-12-24", "2021-12-27", "2021-12-28"}),
        ]
        for start, end, expected in cases:
            with self.subTest(start=start):
                self.assertEqual(research_data.expected_publication_dates(start, end), expected)

    def test_leap_day_and_recent_full_year_counts(self):
        self.assertEqual(research_data.expected_publication_dates("2012-02-29", "2012-02-29"), {"2012-02-29"})
        self.assertEqual(research_data.expected_publication_dates("2024-02-29", "2024-02-29"), {"2024-02-29"})
        self.assertEqual(len(research_data.expected_publication_dates("2024-01-01", "2024-12-31")), 256)
        self.assertEqual(len(research_data.expected_publication_dates("2025-01-01", "2025-12-31")), 255)

    def test_calendar_rejects_unsupported_and_invalid_bounds(self):
        for start, end in (
            ("2009-12-31", "2010-01-01"), ("2025-12-31", "2026-01-01"),
            (END, START), ("20240101", END),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                research_data.expected_publication_dates(start, end)


class QuoteAuditTests(unittest.TestCase):
    def test_complete_valid_quotes_pass_and_report_source_bounds(self):
        report = research_data.audit_quotes(QUOTES, "2024-01-02", "2024-01-03")
        self.assertTrue(report["passed_all_checks"])
        self.assertEqual(report["expected_count"], 2)
        self.assertEqual(report["observed_count"], 2)
        self.assertEqual(report["source_start_date"], "2024-01-02")
        self.assertEqual(report["source_end_date"], "2024-01-03")
        self.assertEqual(report["missing_expected_dates"], [])
        self.assertEqual(report["unexpected_dates"], [])

    def test_missing_and_unexpected_dates_are_reported_independently(self):
        quotes = [{"date": "2024-01-01", "usd_per_eur": 1.0}, QUOTES[0]]
        report = research_data.audit_quotes(quotes, "2024-01-01", "2024-01-03")
        self.assertFalse(report["passed_all_checks"])
        self.assertEqual(report["missing_expected_dates"], ["2024-01-03"])
        self.assertEqual(report["unexpected_dates"], ["2024-01-01"])
        self.assertFalse(report["checks"]["complete_publication_calendar"])
        self.assertFalse(report["checks"]["no_unexpected_dates"])

    def test_bad_order_duplicates_invalid_dates_and_rates_fail_their_checks(self):
        cases = [
            (QUOTES[::-1], "chronological_order"),
            ([QUOTES[0], QUOTES[0]], "unique_dates"),
            ([dict(QUOTES[0], date="not a date")], "valid_iso_dates"),
            ([dict(QUOTES[0], usd_per_eur=float("nan"))], "positive_finite_rates"),
            ([dict(QUOTES[0], usd_per_eur=True)], "positive_finite_rates"),
            ([dict(QUOTES[0], date="2023-12-29")], "within_requested_range"),
        ]
        for quotes, check in cases:
            with self.subTest(check=check):
                report = research_data.audit_quotes(quotes, "2024-01-02", "2024-01-03")
                self.assertFalse(report["passed_all_checks"])
                self.assertFalse(report["checks"][check])

    def test_empty_quotes_fail_even_for_a_day_without_publication(self):
        report = research_data.audit_quotes([], "2024-01-01", "2024-01-01")
        self.assertFalse(report["passed_all_checks"])
        self.assertFalse(report["checks"]["nonempty"])
        self.assertEqual(report["expected_count"], 0)
        self.assertEqual(report["observed_count"], 0)
        self.assertIsNone(report["source_start_date"])
        self.assertIsNone(report["source_end_date"])


if __name__ == "__main__":
    unittest.main()
