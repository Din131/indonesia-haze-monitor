"""Configuration for the Indonesia haze monitor."""
import os
from pathlib import Path

# ---- Sources -------------------------------------------------------------
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}"
FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
FIRMS_DAYS = 2                       # each run re-reads the last 48 hours
BBOX = (94.5, -11.5, 141.5, 6.5)     # west, south, east, north (Indonesia)
KEEP_CONFIDENCE = {"n", "h"}         # VIIRS nominal + high; low-confidence detections are dropped

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

BOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM1/"

# Cities most affected by forest-fire haze, plus neighbours hit by transboundary haze.
CITIES = [
    ("Medan", 3.5952, 98.6722, "Indonesia"),
    ("Pekanbaru", 0.5071, 101.4478, "Indonesia"),
    ("Jambi", -1.6101, 103.6131, "Indonesia"),
    ("Palembang", -2.9761, 104.7754, "Indonesia"),
    ("Pontianak", -0.0263, 109.3425, "Indonesia"),
    ("Palangka Raya", -2.2136, 113.9108, "Indonesia"),
    ("Banjarmasin", -3.3186, 114.5944, "Indonesia"),
    ("Samarinda", -0.5022, 117.1536, "Indonesia"),
    ("Jakarta", -6.2088, 106.8456, "Indonesia"),
    ("Singapore", 1.3521, 103.8198, "Singapore"),
    ("Kuala Lumpur", 3.1390, 101.6869, "Malaysia"),
    ("Kuching", 1.5533, 110.3592, "Malaysia"),
]

# Coarse grid for wind arrows over Sumatra and Kalimantan, where most fires burn.
WIND_GRID = [(lat, lon) for lat in (-5.0, -2.5, 0.0, 2.5, 5.0) for lon in (96.0, 99.0, 102.0, 105.0, 108.0, 111.0, 114.0, 117.0)]

# ---- Retention -----------------------------------------------------------
RECENT_DAYS = 7          # detailed hotspot points kept for the map
TZ_OFFSET_HOURS = 7      # WIB

# ---- Paths ---------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REF = DATA / "reference"
BOUNDARIES_FILE = REF / "idn_adm1.geojson"
HOTSPOTS_RECENT = DATA / "hotspots_recent.csv"
HOTSPOTS_DAILY = DATA / "hotspots_daily_by_province.csv"
AIR_QUALITY = DATA / "air_quality_hourly.csv"
RUN_LOG = DATA / "run_log.csv"
SITE = ROOT / "docs" / "data"
