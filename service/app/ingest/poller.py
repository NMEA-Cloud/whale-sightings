from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from redis import Redis

from app.ingest.config import IngestSettings, get_ingest_settings
from app.ingest.hydra_token_client import HydraTokenClient
from app.ingest.mapping import to_sighting_create, wa_status_to_moderation_status
from app.ingest.service_client import ServiceClient
from app.ingest.whale_alert_client import ALL_STATUSES, WhaleAlertClient

logger = logging.getLogger(__name__)

# Permanent memory of upstream ids Whale Alert has marked Deleted — once removed, our own
# by-source lookup 404s again, and Whale Alert will likely keep returning that same upstream
# sighting on future re-scans within the lookback window without this. The connector's own
# bookkeeping, not SightingRecord data, so reading/writing it directly via Valkey doesn't
# conflict with "sighting writes always go through the real API" (no MQTT/WS implications).
RETIRED_SET_KEY = "ingest:whale_alert:retired"


def run_poll_cycle(
    settings: IngestSettings,
    whale_alert: WhaleAlertClient,
    service: ServiceClient,
    redis_client: Redis,
) -> None:
    """One full pass: re-scan the fixed trailing lookback window across all four Whale Alert
    statuses (no forward cursor is possible — see the plan's Context section), and for each
    result, create/update/delete our own record to match. Deliberately brute-force by
    design for this first pass — see the plan's "Deferred optimization" note about narrowing
    the re-scan window later."""
    start = (datetime.now(timezone.utc) - timedelta(days=settings.whale_alert_lookback_days)).strftime("%Y-%m-%d")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for wa_result in whale_alert.iter_all_sightings(
        statuses=ALL_STATUSES, bbox=settings.whale_alert_bbox, start=start, end=end
    ):
        _process_result(wa_result, service, redis_client)


def _process_result(wa_result: dict, service: ServiceClient, redis_client: Redis) -> None:
    upstream_id = str(wa_result["id"])

    if redis_client.sismember(RETIRED_SET_KEY, upstream_id):
        return  # permanently gone — never recreate

    mapped_status = wa_status_to_moderation_status(wa_result["moderated"])
    existing = service.get_by_source(upstream_id)

    if mapped_status is None:  # Whale Alert status 3, Deleted
        if existing is not None:
            service.delete(existing["id"])
            logger.info("Deleted sighting %s (whale_alert id=%s)", existing["id"], upstream_id)
        redis_client.sadd(RETIRED_SET_KEY, upstream_id)
        return

    if existing is None:
        payload = to_sighting_create(wa_result, mapped_status).model_dump(mode="json")
        created = service.create(payload)
        logger.info("Created sighting %s (whale_alert id=%s)", created["id"], upstream_id)
    elif existing["moderation_status"] != mapped_status.value:
        service.update_moderation(existing["id"], mapped_status.value)
        logger.info(
            "Updated sighting %s to %s (whale_alert id=%s)", existing["id"], mapped_status.value, upstream_id
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_ingest_settings()

    with (
        httpx.Client(verify=settings.ingest_ca_bundle_path or True) as service_http_client,
        httpx.Client() as whale_alert_http_client,
    ):
        token_client = HydraTokenClient(settings, service_http_client)
        service = ServiceClient(settings, service_http_client, token_client)
        whale_alert = WhaleAlertClient(settings, whale_alert_http_client)
        redis_client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)

        logger.info(
            "whale-alert-connector starting — polling every %ss, bbox=%s, lookback=%sd",
            settings.whale_alert_poll_interval_seconds,
            settings.whale_alert_bbox,
            settings.whale_alert_lookback_days,
        )
        while True:
            try:
                run_poll_cycle(settings, whale_alert, service, redis_client)
            except Exception:
                logger.exception("Poll cycle failed")
            time.sleep(settings.whale_alert_poll_interval_seconds)


if __name__ == "__main__":
    main()
