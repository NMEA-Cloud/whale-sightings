import fakeredis
import pytest

from app.ingest.config import IngestSettings
from app.ingest.poller import RETIRED_SET_KEY, _process_result, run_poll_cycle


class FakeWhaleAlertClient:
    def __init__(self, results):
        self._results = results
        self.last_call_kwargs = None

    def iter_all_sightings(self, **kwargs):
        self.last_call_kwargs = kwargs
        return iter(self._results)


class FakeServiceClient:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []
        self.delete_calls = []
        self._by_source: dict[str, dict] = {}

    def seed(self, upstream_id: str, record: dict) -> None:
        self._by_source[upstream_id] = record

    def get_by_source(self, upstream_id):
        return self._by_source.get(upstream_id)

    def create(self, payload):
        self.create_calls.append(payload)
        record = {"id": f"new-{len(self.create_calls)}", "moderation_status": payload["source_moderation_status"]}
        self._by_source[payload["source_upstream_id"]] = record
        return record

    def update_moderation(self, sighting_id, moderation_status):
        self.update_calls.append((sighting_id, moderation_status))
        for record in self._by_source.values():
            if record["id"] == sighting_id:
                record["moderation_status"] = moderation_status
        return {}

    def delete(self, sighting_id):
        self.delete_calls.append(sighting_id)


def make_result(id_=116308, moderated=0, **overrides):
    return {
        "id": id_,
        "created": "2026-08-03 14:13:00",
        "species": "Humpback",
        "species_id": "humpback_whale",
        "lat": 47.7,
        "lng": -122.6,
        "moderated": moderated,
        "comments": "",
        "animal_status": "Live",
        **overrides,
    }


@pytest.fixture
def redis_client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def service():
    return FakeServiceClient()


def test_new_sighting_creates_record(service, redis_client):
    _process_result(make_result(moderated=0), service, redis_client)

    assert len(service.create_calls) == 1
    payload = service.create_calls[0]
    assert payload["source_upstream_id"] == "116308"
    assert payload["source_moderation_status"] == "unreviewed"
    assert service.update_calls == []
    assert service.delete_calls == []


def test_existing_sighting_with_changed_status_is_updated(service, redis_client):
    service.seed("116308", {"id": "existing-1", "moderation_status": "unreviewed"})

    _process_result(make_result(moderated=1), service, redis_client)

    assert service.update_calls == [("existing-1", "confirmed")]
    assert service.create_calls == []
    assert service.delete_calls == []


def test_existing_sighting_with_unchanged_status_is_left_alone(service, redis_client):
    service.seed("116308", {"id": "existing-1", "moderation_status": "confirmed"})

    _process_result(make_result(moderated=1), service, redis_client)

    assert service.update_calls == []
    assert service.create_calls == []


def test_deleted_status_deletes_existing_and_marks_retired(service, redis_client):
    service.seed("116308", {"id": "existing-1", "moderation_status": "confirmed"})

    _process_result(make_result(moderated=3), service, redis_client)

    assert service.delete_calls == ["existing-1"]
    assert redis_client.sismember(RETIRED_SET_KEY, "116308")


def test_deleted_status_with_no_existing_record_still_marks_retired(service, redis_client):
    _process_result(make_result(moderated=3), service, redis_client)

    assert service.delete_calls == []
    assert redis_client.sismember(RETIRED_SET_KEY, "116308")


def test_retired_upstream_id_is_skipped_entirely(service, redis_client):
    redis_client.sadd(RETIRED_SET_KEY, "116308")

    _process_result(make_result(moderated=0), service, redis_client)

    assert service.create_calls == []
    assert service.update_calls == []
    assert service.delete_calls == []


def test_run_poll_cycle_queries_all_statuses_and_configured_bbox(redis_client):
    settings = IngestSettings(
        whale_alert_client_id="wa-id",
        whale_alert_client_secret="wa-secret",
        ingest_hydra_client_id="hydra-id",
        ingest_hydra_client_secret="hydra-secret",
        whale_alert_bbox="-123.3,47.0,-122.0,48.8",
        whale_alert_lookback_days=14,
    )
    whale_alert = FakeWhaleAlertClient([make_result()])
    service = FakeServiceClient()

    run_poll_cycle(settings, whale_alert, service, redis_client)

    assert whale_alert.last_call_kwargs["statuses"] == (0, 1, 2, 3)
    assert whale_alert.last_call_kwargs["bbox"] == "-123.3,47.0,-122.0,48.8"
    assert len(service.create_calls) == 1
