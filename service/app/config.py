from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    valkey_host: str = "localhost"
    valkey_port: int = 6379
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "whale-sightings/updates"
    cors_origins: str = "http://localhost:8080"
    # Used to build the resource link published in MQTT messages (see PahoMqttPublisher) —
    # must be an address subscribers can actually reach, not necessarily where the service
    # binds internally.
    public_api_base_url: str = "https://localhost:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    return Settings()
