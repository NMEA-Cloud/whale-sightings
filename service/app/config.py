from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    valkey_host: str = "localhost"
    valkey_port: int = 6379
    mqtt_host: str = "localhost"
    mqtt_port: int = 8883
    mqtt_topic: str = "whale-sightings/updates"
    # Trusted for the TLS connection to the broker. Unset (the default) means plain,
    # unencrypted MQTT — used by tests and any non-Docker run against a broker without TLS
    # configured. docker-compose.yml sets this, since the broker there requires TLS.
    mqtt_ca_bundle_path: str | None = None
    cors_origins: str = "http://localhost:8080"
    # Optional: matched against the Origin header in addition to cors_origins, for allowing
    # a whole range of hosts (e.g. a LAN subnet) without enumerating each one, e.g.
    # ^http://192\.168\.0\.\d{1,3}:(8080|8081)$
    cors_origin_regex: str | None = None
    # Used to build the resource link published in MQTT messages (see PahoMqttPublisher) —
    # must be an address subscribers can actually reach, not necessarily where the service
    # binds internally.
    public_api_base_url: str = "https://localhost:8000"
    # The only setting that changes if the OAuth2 authorization server (Ory Hydra) relocates
    # to a different LAN machine — mirrors the public_api_base_url pattern above. This is the
    # AS's public identity: it's checked against the "iss" claim on every token and published
    # in the RFC 9728 resource-metadata doc, so it must be the same address browsers use.
    oauth_issuer_url: str = "https://localhost:4444"
    # Where this container itself fetches the JWKS keyset from, when that differs from
    # oauth_issuer_url. Only needed for the default docker-compose.yml topology, where
    # hydra's browser-facing issuer is "localhost" (meaningless from inside another
    # container) but it's reachable from here as "hydra" on the Docker network. Falls back
    # to oauth_issuer_url when unset — which is what a relocated AS at a real LAN address
    # should do, since that address is reachable from both the browser and this container.
    # Never needs to change on relocation; oauth_issuer_url remains the only knob for that.
    oauth_jwks_url: str | None = None
    # Expected "aud" claim on access tokens — matches public_api_base_url by convention,
    # since that's the resource these tokens are scoped to.
    oauth_expected_audience: str = "https://localhost:8000"
    # Trusted for both the oauth_jwks_url fetch above and, if set, for a relocated AS on a
    # different machine whose TLS cert is signed by a CA this container doesn't already
    # trust — see the README's cross-machine TLS setup.
    oauth_ca_bundle_path: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    return Settings()
