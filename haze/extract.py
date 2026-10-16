"""Extract: satellite fire hotspots (NASA FIRMS), air quality and wind (Open-Meteo)."""
import csv
import io
import logging
import urllib.parse

from . import http
from .config import (AIR_QUALITY_URL, BBOX, BOUNDARIES_API, CITIES, FIRMS_DAYS, FIRMS_MAP_KEY,
                     FIRMS_SOURCES, FIRMS_URL, WEATHER_URL, WIND_GRID)

log = logging.getLogger("haze")


def fetch_hotspots() -> list[dict]:
    """Return raw FIRMS rows from every VIIRS source. Fails only if all sources fail."""
    if not FIRMS_MAP_KEY:
        raise RuntimeError("FIRMS_MAP_KEY is not set")
    bbox = ",".join(str(v) for v in BBOX)
    rows, ok, problems = [], 0, []
    for source in FIRMS_SOURCES:
        url = FIRMS_URL.format(key=FIRMS_MAP_KEY, source=source, bbox=bbox, days=FIRMS_DAYS)
        try:
            text = http.get(url).decode("utf-8", "replace")
        except RuntimeError as exc:
            log.warning("FIRMS %s: %s", source, exc)
            problems.append(f"{source}: {exc}")
            continue
        if not text.startswith("latitude"):
            log.warning("FIRMS %s returned no CSV (%s)", source, text[:80].strip())
            problems.append(f"{source}: {text[:80].strip()}")
            continue
        ok += 1
        part = list(csv.DictReader(io.StringIO(text)))
        for r in part:
            r["source"] = source
        rows.extend(part)
        log.info("FIRMS %s: %d detections", source, len(part))
    if ok == 0:
        raise RuntimeError("no FIRMS source could be read; " + " | ".join(problems))
    return rows


def _multi(url: str, points: list[tuple[float, float]], params: dict) -> list[dict]:
    q = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        **params,
    }
    data = http.get_json(f"{url}?{urllib.parse.urlencode(q)}")
    return data if isinstance(data, list) else [data]


def fetch_air_quality() -> list[dict]:
    """Hourly PM2.5 / PM10 for each city (CAMS model via Open-Meteo), last 2 days + today."""
    points = [(lat, lon) for _, lat, lon, _ in CITIES]
    return _multi(AIR_QUALITY_URL, points, {
        "hourly": "pm2_5,pm10",
        "past_days": 2,
        "forecast_days": 1,
        "timezone": "Asia/Jakarta",
    })


def fetch_wind() -> list[dict]:
    """Current 10 m wind speed and direction on a coarse grid."""
    return _multi(WEATHER_URL, WIND_GRID, {
        "current": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "kmh",
        "timezone": "Asia/Jakarta",
    })


def fetch_boundaries() -> dict:
    """Province (ADM1) boundaries of Indonesia from geoBoundaries (simplified)."""
    meta = http.get_json(BOUNDARIES_API)
    return http.get_json(meta["simplifiedGeometryGeoJSON"], timeout=120)
