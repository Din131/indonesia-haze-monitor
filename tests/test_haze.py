"""Offline tests with small fixtures; no network or API key needed."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from haze import config, run, transform, validate
from haze.geo import ProvinceIndex

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)  # 13:00 WIB

# Two square "provinces" with a hole in the second one.
BOUNDARIES = {"type": "FeatureCollection", "features": [
    {"properties": {"shapeName": "Riau"}, "geometry": {"type": "Polygon", "coordinates": [[[100, -1], [103, -1], [103, 2], [100, 2], [100, -1]]]}},
    {"properties": {"shapeName": "Central Kalimantan"}, "geometry": {"type": "MultiPolygon", "coordinates": [[
        [[111, -4], [115, -4], [115, 0], [111, 0], [111, -4]],
        [[112, -3], [113, -3], [113, -2], [112, -2], [112, -3]],
    ]]}},
]}

FIRMS = [
    {"latitude": "0.5", "longitude": "101.5", "acq_date": "2026-10-16", "acq_time": "530", "confidence": "h", "frp": "12.3", "daynight": "D", "source": "VIIRS_NOAA20_NRT"},
    {"latitude": "-1.0", "longitude": "114.0", "acq_date": "2026-10-15", "acq_time": "1820", "confidence": "n", "frp": "4.0", "daynight": "N", "source": "VIIRS_SNPP_NRT"},
    {"latitude": "-2.5", "longitude": "112.5", "acq_date": "2026-10-15", "acq_time": "1820", "confidence": "n", "frp": "3.0", "daynight": "N", "source": "VIIRS_SNPP_NRT"},
    {"latitude": "0.6", "longitude": "101.6", "acq_date": "2026-10-16", "acq_time": "0530", "confidence": "l", "frp": "1.0", "daynight": "D", "source": "VIIRS_NOAA20_NRT"},
]


def aq_payload():
    times = [f"2026-10-16T{h:02d}:00" for h in range(24)]
    return [{"hourly": {"time": times, "pm2_5": [40.0 + i for i in range(24)], "pm10": [60.0] * 24}} for _ in config.CITIES]


WIND = [{"latitude": 0.0, "longitude": 102.0, "current": {"wind_speed_10m": 12.0, "wind_direction_10m": 135}}]


class GeoTest(unittest.TestCase):
    def setUp(self):
        self.idx = ProvinceIndex(BOUNDARIES)

    def test_point_inside(self):
        self.assertEqual(self.idx.lookup(101.5, 0.5), "Riau")

    def test_point_in_hole_is_outside(self):
        self.assertEqual(self.idx.lookup(112.5, -2.5), "Luar Indonesia")

    def test_multipolygon(self):
        self.assertEqual(self.idx.lookup(114.0, -1.0), "Kalimantan Tengah")


class TransformTest(unittest.TestCase):
    def setUp(self):
        self.rows = transform.clean_hotspots(FIRMS, ProvinceIndex(BOUNDARIES))

    def test_low_confidence_dropped(self):
        self.assertEqual(len(self.rows), 3)

    def test_local_time_and_date(self):
        r = next(r for r in self.rows if r["province"] == "Kalimantan Tengah")
        self.assertEqual((r["date_wib"], r["time_wib"]), ("2026-10-16", "01:20"))  # 18:20 UTC + 7h

    def test_short_acq_time_is_padded(self):
        r = next(r for r in self.rows if r["province"] == "Riau")
        self.assertEqual(r["time_wib"], "12:30")

    def test_merge_drops_old_and_duplicates(self):
        old = dict(self.rows[0], id="old", acq_utc="2026-10-01T00:00+00:00")
        merged = transform.merge_recent([old, self.rows[0]], self.rows, NOW)
        self.assertEqual(len(merged), 3)

    def test_daily_counts(self):
        daily = transform.daily_by_province([], self.rows, NOW)
        riau = next(d for d in daily if d["province"] == "Riau")
        self.assertEqual((riau["hotspots"], riau["high_confidence"]), (1, 1))

    def test_pm25_category(self):
        self.assertEqual(transform.pm25_category(40.0), "Unhealthy for sensitive groups")
        self.assertEqual(transform.pm25_category(8.0), "Good")


class ValidateTest(unittest.TestCase):
    def test_outside_bbox_flagged(self):
        rows = transform.clean_hotspots(FIRMS, ProvinceIndex(BOUNDARIES))
        rows[0]["longitude"] = 150.0
        self.assertTrue(any("outside" in i for i in validate.hotspot_issues(rows, NOW)))

    def test_bad_pm25_flagged(self):
        rows = [{"time_wib": "2026-10-16T00:00", "city": c[0], "pm2_5": -5} for c in config.CITIES]
        self.assertTrue(validate.air_quality_issues(rows))


class EndToEndTest(unittest.TestCase):
    def _run(self, tmp: Path, firms=FIRMS):
        (tmp / "b.geojson").write_text(json.dumps(BOUNDARIES))
        patches = [
            mock.patch.object(run, "BOUNDARIES_FILE", tmp / "b.geojson"),
            mock.patch.object(run, "HOTSPOTS_RECENT", tmp / "recent.csv"),
            mock.patch.object(run, "HOTSPOTS_DAILY", tmp / "daily.csv"),
            mock.patch.object(run, "AIR_QUALITY", tmp / "aq.csv"),
            mock.patch.object(run, "RUN_LOG", tmp / "log.csv"),
            mock.patch.object(run, "SITE", tmp / "site"),
            mock.patch.object(run.extract, "fetch_hotspots", return_value=firms),
            mock.patch.object(run.extract, "fetch_air_quality", return_value=aq_payload()),
            mock.patch.object(run.extract, "fetch_wind", return_value=WIND),
        ]
        for p in patches:
            p.start()
        try:
            return run.main(NOW)
        finally:
            for p in patches:
                p.stop()

    def test_full_run(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self.assertEqual(self._run(tmp), 0)
            summary = json.loads((tmp / "site" / "summary.json").read_text())
            self.assertEqual(summary["hotspots_7d"], 3)
            self.assertEqual(summary["provinces_24h"][0]["province"], "Riau")
            geo = json.loads((tmp / "site" / "hotspots.geojson").read_text())
            self.assertEqual(len(geo["features"]), 3)
            aq = json.loads((tmp / "site" / "air_quality.json").read_text())
            self.assertEqual(aq[0]["time_wib"], "2026-10-16T13:00")  # nothing after "now" is used
            # A second identical run must not duplicate anything (idempotent).
            self.assertEqual(self._run(tmp), 0)
            with (tmp / "recent.csv").open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 3)

    def test_failed_validation_writes_nothing(self):
        bad = [dict(FIRMS[0], latitude="45.0")]
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self.assertEqual(self._run(tmp, bad), 1)
            self.assertFalse((tmp / "recent.csv").exists())
            with (tmp / "log.csv").open() as f:
                self.assertTrue(list(csv.DictReader(f))[-1]["status"].startswith("failed"))


if __name__ == "__main__":
    unittest.main()
