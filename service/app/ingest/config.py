from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    """Settings for the whale-alert-connector process only (see poller.py) — deliberately
    kept out of app/config.py's Settings class, since the main FastAPI process never reads
    any of these. env_file here is only exercised for a standalone/non-Docker run; the
    docker-compose.yml service instead injects these via its own env_file: directive
    pointing at the same gitignored service/.env.whale-alert-connector."""

    model_config = SettingsConfigDict(env_file=".env.whale-alert-connector", extra="ignore")

    # Whale Alert — the only settings whale_alert_client.py (the one file that ever calls
    # the real Whale Alert service) reads.
    whale_alert_api_base_url: str = "https://seereportsave.org/whalealert/api/v1"
    whale_alert_client_id: str
    whale_alert_client_secret: str
    # west,south,east,north — greater Puget Sound plus the San Juan Islands. Confirmed via a
    # real saved example that Whale Alert's bbox is an explicit, real filter, not something
    # applied automatically by the caller's own location.
    whale_alert_bbox: str = "-123.3,47.0,-122.0,48.8"
    # No forward-moving cursor is possible (Whale Alert's schema has no "last modified"
    # field — see the plan's Context section), so every cycle re-scans this fixed trailing
    # window across all four statuses instead.
    whale_alert_lookback_days: int = 14
    whale_alert_poll_interval_seconds: int = 300

    # Our own service (service_client.py) — real HTTP, same as every other client in this repo.
    ingest_service_api_base: str = "https://service:8000"
    ingest_ca_bundle_path: str | None = None

    # Our own Hydra (hydra_token_client.py) — client_credentials, scope sightings:ingest.
    # Not to be confused with the Whale Alert credentials above; this authenticates the
    # connector *to our own service*, a completely separate credential pair.
    ingest_hydra_token_url: str = "https://hydra:4444/oauth2/token"
    ingest_hydra_client_id: str
    ingest_hydra_client_secret: str
    ingest_hydra_audience: str = "https://api.dev.wombat-sightings.org:8000"

    # Valkey — used only for this connector's own "retired" bookkeeping set (see poller.py),
    # never for SightingRecord data itself (that always goes through service_client.py).
    valkey_host: str = "valkey"
    valkey_port: int = 6379


def get_ingest_settings() -> IngestSettings:
    return IngestSettings()
