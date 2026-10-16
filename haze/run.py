"""Entry point: python -m haze.run"""
import json
import logging
import sys
from datetime import datetime, timezone

from . import extract, load, transform, validate
from .config import (AIR_QUALITY, BOUNDARIES_FILE, FIRMS_MAP_KEY, HOTSPOTS_DAILY, HOTSPOTS_RECENT, RUN_LOG, SITE)
from .geo import ProvinceIndex, indonesian

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
    status, error, stage = "success", "", "start"
    try:
        stage = "boundaries"
        provinces = province_index()

        stage = "hotspots"
        raw = extract.fetch_hotspots()
        stage = "province lookup"
        new_hotspots = transform.clean_hotspots(raw, provinces)
        stats["hotspots_fetched"] = len(new_hotspots)
        old_recent = load.read_csv(HOTSPOTS_RECENT)
        old_daily = load.read_csv(HOTSPOTS_DAILY)
        for row in old_recent + old_daily:   # older rows may still carry English names
            row["province"] = indonesian(row["province"])
        recent = transform.merge_recent(old_recent, new_hotspots, now_utc)
        daily = transform.daily_by_province(old_daily, recent, now_utc)

        stage = "air quality"
        aq_new = transform.air_quality_rows(extract.fetch_air_quality())
        aq_all = load.upsert_air_quality(load.read_csv(AIR_QUALITY), aq_new)
        stage = "wind"
        wind = transform.wind_points(extract.fetch_wind())

        stage = "validate"
        validate.assert_clean(validate.hotspot_issues(recent, now_utc) + validate.air_quality_issues(aq_new))

        stage = "load"
        load.write_csv(HOTSPOTS_RECENT, recent, transform.HOTSPOT_FIELDS)
        load.write_csv(HOTSPOTS_DAILY, daily, load.DAILY_FIELDS)
        load.write_csv(AIR_QUALITY, aq_all, load.AQ_FIELDS)
        summary = load.publish(SITE, recent, daily, aq_all, wind, now_utc)
        stats.update(hotspots_7d=len(recent), aq_rows=len(aq_new))
        log.info("Loaded %d hotspot detections (%d hotspots fetched this run)", len(recent), len(new_hotspots))
        log.info("Hotspots: %d in 24h, %d in 7 days", summary["hotspots_24h"], summary["hotspots_7d"])
    except Exception as exc:  # noqa: BLE001 - logged, recorded, then surfaced as exit code
        status = f"failed at {stage}: {type(exc).__name__}"
        error = str(exc).replace(FIRMS_MAP_KEY, "***") if FIRMS_MAP_KEY else str(exc)
        error = " ".join(error.split())[:300]
        log.exception("Pipeline failed at stage '%s'", stage)
    finally:
        load.append_csv(RUN_LOG, {"run_at_utc": now_utc.isoformat(timespec="minutes"), **stats, "status": status, "error": error})
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
