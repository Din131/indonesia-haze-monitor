"""Entry point: python -m haze.run"""
import json
import logging
import sys
from datetime import datetime, timezone

from . import extract, load, transform, validate
from .config import (AIR_QUALITY, BOUNDARIES_FILE, HOTSPOTS_DAILY, HOTSPOTS_RECENT, RUN_LOG, SITE)
from .geo import ProvinceIndex

log = logging.getLogger("haze")


def province_index() -> ProvinceIndex:
    if not BOUNDARIES_FILE.exists():
        log.info("Downloading province boundaries (first run only)")
        BOUNDARIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOUNDARIES_FILE.write_text(json.dumps(extract.fetch_boundaries(), separators=(",", ":")), encoding="utf-8")
    return ProvinceIndex(json.loads(BOUNDARIES_FILE.read_text(encoding="utf-8")))


def main(now_utc: datetime | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now_utc = now_utc or datetime.now(timezone.utc).replace(second=0, microsecond=0)
    stats = {"hotspots_fetched": 0, "hotspots_7d": 0, "aq_rows": 0}
    status = "success"
    try:
        provinces = province_index()

        raw = extract.fetch_hotspots()
        new_hotspots = transform.clean_hotspots(raw, provinces)
        stats["hotspots_fetched"] = len(new_hotspots)
        recent = transform.merge_recent(load.read_csv(HOTSPOTS_RECENT), new_hotspots, now_utc)
        daily = transform.daily_by_province(load.read_csv(HOTSPOTS_DAILY), recent, now_utc)

        aq_new = transform.air_quality_rows(extract.fetch_air_quality())
        aq_all = load.upsert_air_quality(load.read_csv(AIR_QUALITY), aq_new)
        wind = transform.wind_points(extract.fetch_wind())

        validate.assert_clean(validate.hotspot_issues(recent, now_utc) + validate.air_quality_issues(aq_new))

        load.write_csv(HOTSPOTS_RECENT, recent, transform.HOTSPOT_FIELDS)
        load.write_csv(HOTSPOTS_DAILY, daily, load.DAILY_FIELDS)
        load.write_csv(AIR_QUALITY, aq_all, load.AQ_FIELDS)
        summary = load.publish(SITE, recent, daily, aq_all, wind, now_utc)
        stats.update(hotspots_7d=len(recent), aq_rows=len(aq_new))
        log.info("Hotspots: %d in 24h, %d in 7 days", summary["hotspots_24h"], summary["hotspots_7d"])
    except Exception as exc:  # noqa: BLE001 - logged, recorded, then surfaced as exit code
        status = f"failed: {type(exc).__name__}"
        log.error("%s", exc)
    finally:
        load.append_csv(RUN_LOG, {"run_at_utc": now_utc.isoformat(timespec="minutes"), **stats, "status": status})
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
