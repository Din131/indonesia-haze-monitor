"""Transform: clean hotspots, add province and local time, aggregate, shape air-quality rows."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .config import CITIES, KEEP_CONFIDENCE, RECENT_DAYS, TZ_OFFSET_HOURS

WIB = timezone(timedelta(hours=TZ_OFFSET_HOURS))
SATELLITE = {"VIIRS_SNPP_NRT": "Suomi NPP", "VIIRS_NOAA20_NRT": "NOAA-20", "VIIRS_NOAA21_NRT": "NOAA-21"}
HOTSPOT_FIELDS = ["id", "satellite", "latitude", "longitude", "acq_utc", "date_wib", "time_wib",
                  "confidence", "frp", "daynight", "province"]


def clean_hotspots(raw: list[dict], provinces) -> list[dict]:
    out = []
    for r in raw:
        conf = str(r.get("confidence", "")).strip().lower()[:1]
        if conf not in KEEP_CONFIDENCE:
            continue
        try:
            lat, lon = round(float(r["latitude"]), 4), round(float(r["longitude"]), 4)
            hhmm = str(r["acq_time"]).strip().zfill(4)
            utc = datetime.strptime(f'{r["acq_date"]} {hhmm}', "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            frp = float(r.get("frp") or 0)
        except (KeyError, ValueError):
            continue
        local = utc.astimezone(WIB)
        sat = SATELLITE.get(r.get("source", ""), r.get("source", ""))
        out.append({
            "id": f"{sat}|{lat}|{lon}|{utc:%Y%m%d%H%M}",
            "satellite": sat,
            "latitude": lat,
            "longitude": lon,
            "acq_utc": utc.isoformat(timespec="minutes"),
            "date_wib": local.date().isoformat(),
            "time_wib": local.strftime("%H:%M"),
            "confidence": "high" if conf == "h" else "nominal",
            "frp": round(frp, 1),
            "daynight": r.get("daynight", ""),
            "province": provinces.lookup(lon, lat),
        })
    return out


def merge_recent(existing: list[dict], new: list[dict], now_utc: datetime) -> list[dict]:
    """Union on id, keep only the last RECENT_DAYS, newest first."""
    cutoff = now_utc - timedelta(days=RECENT_DAYS)
    merged = {r["id"]: r for r in existing}
    merged.update({r["id"]: r for r in new})
    keep = [r for r in merged.values() if datetime.fromisoformat(r["acq_utc"]) >= cutoff]
    return sorted(keep, key=lambda r: (r["acq_utc"], r["id"]), reverse=True)


def recompute_from(now_utc: datetime) -> str:
    """First WIB date that the recent window covers completely enough to recompute."""
    return (now_utc.astimezone(WIB) - timedelta(days=RECENT_DAYS - 1)).date().isoformat()


def daily_by_province(history: list[dict], recent: list[dict], now_utc: datetime) -> list[dict]:
    """Rebuild daily counts for dates inside the recent window, keep older history as is."""
    start = recompute_from(now_utc)
    counts = defaultdict(lambda: [0, 0])
    for r in recent:
        if r["date_wib"] >= start:
            c = counts[(r["date_wib"], r["province"])]
            c[0] += 1
            c[1] += r["confidence"] == "high"
    rows = [h for h in history if h["date_wib"] < start]
    rows += [{"date_wib": d, "province": p, "hotspots": n, "high_confidence": hc} for (d, p), (n, hc) in counts.items()]
    return sorted(rows, key=lambda r: (r["date_wib"], r["province"]))


def air_quality_rows(payload: list[dict]) -> list[dict]:
    rows = []
    for (name, _, _, _), loc in zip(CITIES, payload):
        h = loc.get("hourly", {})
        for t, pm25, pm10 in zip(h.get("time", []), h.get("pm2_5", []), h.get("pm10", [])):
            if pm25 is None:
                continue
            rows.append({"time_wib": t, "city": name, "pm2_5": round(pm25, 1), "pm10": None if pm10 is None else round(pm10, 1)})
    return rows


def wind_points(payload: list[dict]) -> list[dict]:
    out = []
    for loc in payload:
        cur = loc.get("current", {})
        if cur.get("wind_speed_10m") is None:
            continue
        out.append({"lat": loc["latitude"], "lon": loc["longitude"],
                    "speed_kmh": cur["wind_speed_10m"], "from_deg": cur["wind_direction_10m"]})
    return out


# US EPA PM2.5 (24-hour) categories, 2024 breakpoints.
PM25_CATEGORIES = [
    (9.0, "Good"), (35.4, "Moderate"), (55.4, "Unhealthy for sensitive groups"),
    (125.4, "Unhealthy"), (225.4, "Very unhealthy"), (float("inf"), "Hazardous"),
]


def pm25_category(value: float | None) -> str | None:
    if value is None:
        return None
    return next(label for limit, label in PM25_CATEGORIES if value <= limit)
