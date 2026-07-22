from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    valkey_host: str = "localhost"
    valkey_port: int = 6379
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "whale-sightings/updates"
    cors_origins: str = "http://localhost:8080"
    # Optional: matched against the Origin header in addition to cors_origins, for allowing
    # a whole range of hosts (e.g. a LAN subnet) without enumerating each one, e.g.
    # ^http://192\.168\.0\.\d{1,3}:(8080|8081)$
    cors_origin_regex: str | None = None
    # Used to build the resource link published in MQTT messages (see PahoMqttPublisher) —
    # must be an address subscribers can actually reach, not necessarily where the service
    # binds internally.
    public_api_base_url: str = "https://localhost:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    return Settings()
