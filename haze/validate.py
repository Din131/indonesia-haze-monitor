"""Validate: data-quality checks that block a bad load."""
from datetime import datetime, timedelta

from .config import BBOX, CITIES


class ValidationError(Exception):
    pass


def hotspot_issues(rows: list[dict], now_utc: datetime) -> list[str]:
    issues, seen = [], set()
    west, south, east, north = BBOX
    for r in rows:
        if r["id"] in seen:
            issues.append(f"duplicate hotspot {r['id']}")
        seen.add(r["id"])
        if not (west <= float(r["longitude"]) <= east and south <= float(r["latitude"]) <= north):
            issues.append(f"hotspot outside area {r['id']}")
        if float(r["frp"]) < 0:
            issues.append(f"negative fire radiative power {r['id']}")
        if datetime.fromisoformat(r["acq_utc"]) > now_utc + timedelta(hours=1):
            issues.append(f"hotspot in the future {r['id']}")
    return issues


def air_quality_issues(rows: list[dict]) -> list[str]:
    issues = []
    cities = {r["city"] for r in rows}
    missing = {c[0] for c in CITIES} - cities
    if len(missing) > len(CITIES) // 2:
        issues.append(f"air quality missing for most cities: {sorted(missing)}")
    for r in rows:
        # Severe peat-fire haze can push PM2.5 above 2,000 µg/m³ (Palangka Raya, 2015 and 2019),
        # so only negative or physically absurd values are rejected.
        if not 0 <= float(r["pm2_5"]) < 10000:
            issues.append(f"implausible PM2.5 {r['city']} {r['time_wib']}: {r['pm2_5']}")
    return issues


def assert_clean(issues: list[str]) -> None:
    if issues:
        head = "\n  - ".join(issues[:20])
        raise ValidationError(f"{len(issues)} data-quality issue(s):\n  - {head}")
