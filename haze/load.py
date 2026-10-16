"""Load: persist datasets as CSV and publish compact JSON for the dashboard."""
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .config import CITIES
from .geo import OUTSIDE
from .transform import HOTSPOT_FIELDS, WIB, pm25_category

DAILY_FIELDS = ["date_wib", "province", "hotspots", "high_confidence"]
AQ_FIELDS = ["time_wib", "city", "pm2_5", "pm10"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def append_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def upsert_air_quality(existing: list[dict], new: list[dict]) -> list[dict]:
    merged = {(r["time_wib"], r["city"]): r for r in existing}
    merged.update({(r["time_wib"], r["city"]): r for r in new})
    return sorted(merged.values(), key=lambda r: (r["time_wib"], r["city"]))


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def city_air_quality(aq_rows: list[dict], now_utc: datetime) -> list[dict]:
    now_local = now_utc.astimezone(WIB).strftime("%Y-%m-%dT%H:%M")
    by_city = defaultdict(list)
    for r in aq_rows:
        if r["time_wib"] <= now_local:
            by_city[r["city"]].append((r["time_wib"], float(r["pm2_5"])))
    out = []
    for name, lat, lon, country in CITIES:
        series = sorted(by_city.get(name, []))
        if not series:
            continue
        last24 = [v for _, v in series[-24:]]
        mean24 = round(statistics.fmean(last24), 1)
        out.append({
            "city": name, "country": country, "lat": lat, "lon": lon,
            "time_wib": series[-1][0], "pm2_5": series[-1][1],
            "mean_24h": mean24, "category": pm25_category(mean24),
            "series_48h": [[t, v] for t, v in series[-48:]],
        })
    return out


def publish(site: Path, recent: list[dict], daily: list[dict], aq_rows: list[dict], wind: list[dict], now_utc: datetime) -> dict:
    now_local = now_utc.astimezone(WIB)

    features = []
    for r in recent:
        age_h = (now_utc - datetime.fromisoformat(r["acq_utc"])).total_seconds() / 3600
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
            "properties": {"d": r["date_wib"], "t": r["time_wib"], "c": r["confidence"][0], "frp": float(r["frp"]),
                           "sat": r["satellite"], "prov": r["province"], "age": round(age_h, 1)},
        })
    _dump(site / "hotspots.geojson", {"type": "FeatureCollection", "features": features})

    last24 = [f for f in features if f["properties"]["age"] <= 24]
    by_prov = defaultdict(int)
    for f in last24:
        by_prov[f["properties"]["prov"]] += 1

    cities = city_air_quality(aq_rows, now_utc)
    _dump(site / "air_quality.json", cities)
    _dump(site / "wind.json", wind)

    # Daily trend: last 90 days, total plus the five provinces with most hotspots in the last 30 days.
    start90 = (now_local - timedelta(days=89)).date().isoformat()
    start30 = (now_local - timedelta(days=29)).date().isoformat()
    dates = [(now_local - timedelta(days=i)).date().isoformat() for i in range(89, -1, -1)]
    totals = defaultdict(int)
    per_prov = defaultdict(lambda: defaultdict(int))
    prov30 = defaultdict(int)
    for r in daily:
        if r["date_wib"] < start90 or r["province"] == OUTSIDE:
            continue
        n = int(r["hotspots"])
        totals[r["date_wib"]] += n
        per_prov[r["province"]][r["date_wib"]] += n
        if r["date_wib"] >= start30:
            prov30[r["province"]] += n
    top = [p for p, _ in sorted(prov30.items(), key=lambda kv: -kv[1])[:5]]
    _dump(site / "trend.json", {
        "dates": dates,
        "total": [totals.get(d, 0) for d in dates],
        "provinces": {p: [per_prov[p].get(d, 0) for d in dates] for p in top},
    })

    summary = {
        "generated_at_utc": now_utc.isoformat(timespec="minutes"),
        "generated_at_wib": now_local.strftime("%d %b %Y, %H:%M WIB"),
        "latest_detection_wib": f'{recent[0]["date_wib"]} {recent[0]["time_wib"]}' if recent else None,
        "hotspots_24h": len(last24),
        "hotspots_24h_high": sum(1 for f in last24 if f["properties"]["c"] == "h"),
        "hotspots_7d": len(features),
        "provinces_24h": [{"province": p, "hotspots": n} for p, n in sorted(by_prov.items(), key=lambda kv: -kv[1]) if p != OUTSIDE][:10],
        "worst_city": max(cities, key=lambda c: c["mean_24h"]) if cities else None,
        "sources": {
            "hotspots": "NASA FIRMS VIIRS (Suomi NPP, NOAA-20, NOAA-21), nominal and high confidence",
            "air_quality": "Open-Meteo Air Quality API (CAMS global model)",
            "wind": "Open-Meteo Forecast API",
            "boundaries": "geoBoundaries (CC BY 4.0)",
        },
    }
    summary["worst_city"] = {k: v for k, v in summary["worst_city"].items() if k != "series_48h"} if summary["worst_city"] else None
    _dump(site / "summary.json", summary)
    return summary
