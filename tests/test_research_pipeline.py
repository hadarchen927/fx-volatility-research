"""Checks for evaluation boundaries and the local protocol gate (no network)."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forecast_models import forecast_returns, make_interval_returns
import run_research as study


class ProtocolTests(unittest.TestCase):
    def test_final_requires_lock_before_any_data_access(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(study, "LOCK_PATH", Path(folder) / "absent.json"), \
                 patch.object(study, "require_lock", side_effect=ValueError("missing lock")), \
                 patch.object(study, "snapshot") as data:
                with self.assertRaisesRegex(ValueError, "missing lock"):
                    study.run(stage="final", offline=True)
                data.assert_not_called()

    def test_code_change_invalidates_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in study.LOCKED_FILES:
                (root / name).write_text("original", encoding="utf-8")
            lock = root / "lock.json"
            lock.write_text(json.dumps({"file_sha256": study.code_fingerprints(root)}), encoding="utf-8")
            study.require_lock(lock, root)
            (root / "forecast_models.py").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                study.require_lock(lock, root)

    def test_split_uses_target_date_including_boundary_days(self):
        config = study.read_config()
        for value, expected in (("2021-12-31", "development"), ("2022-01-01", "validation"),
                                ("2024-12-31", "validation"), ("2025-01-01", "final")):
            self.assertEqual(study.split_name(value, config), expected)

    def test_first_final_forecast_keeps_previous_year_history(self):
        quotes = [{"date": "2024-12-27", "usd_per_eur": 1.00},
                  {"date": "2024-12-30", "usd_per_eur": 1.01},
                  {"date": "2024-12-31", "usd_per_eur": 1.02},
                  {"date": "2025-01-02", "usd_per_eur": 1.03}]
        forecasts = forecast_returns(make_interval_returns(quotes), window=2)
        first = forecasts[0]
        self.assertEqual(first["date"], "2025-01-02")
        self.assertEqual(first["forecast_origin"], "2024-12-31")
        self.assertEqual(first["calendar_gap_days"], 2)
        expected = (.01 ** 2 + ((1.02 - 1.01) / 1.01) ** 2) / 2
        self.assertAlmostEqual(first["rolling_forecast"], expected)
        quotes[-1]["usd_per_eur"] = 1.50
        changed = forecast_returns(make_interval_returns(quotes), window=2)[0]
        self.assertEqual(first["rolling_forecast"], changed["rolling_forecast"])
        self.assertEqual(first["ewma_forecast"], changed["ewma_forecast"])
        self.assertNotEqual(first["target_squared_return"], changed["target_squared_return"])

    def test_invalid_split_dates_rejected(self):
        config = study.read_config()
        config["final_start"] = "2024-01-01"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                study.read_config(path)

    def test_compact_iso_dates_rejected_before_string_splitting(self):
        config = study.read_config()
        config["development_end"] = "20210630"
        config["validation_start"] = "2021-07-01"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical"):
                study.read_config(path)

    def test_changed_development_data_stops_before_final_download(self):
        lock = {"development_snapshot_sha256": "original"}
        with patch.object(study, "require_lock", return_value=lock), \
             patch.object(study, "snapshot", return_value=([], {"raw_sha256": "changed"})) as data:
            with self.assertRaisesRegex(ValueError, "Development data changed"):
                study.run(stage="final")
            self.assertEqual(data.call_count, 1)

    def test_offline_missing_snapshot_cannot_download(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(study, "ROOT", Path(folder)), patch.object(study, "download_snapshot") as download:
                with self.assertRaisesRegex(ValueError, "Offline mode"):
                    study.snapshot("2010-01-01", "2024-12-31", offline=True)
                download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
