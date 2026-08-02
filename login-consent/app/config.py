from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hydra_admin_url: str = "https://hydra:4445"
    # mkcert's CA root, copied into certs/ by scripts/setup-tls.sh — lets httpx trust
    # Hydra's mkcert-issued cert on the admin API without disabling verification.
    hydra_admin_ca_bundle_path: str = "/certs/rootCA.pem"
    admin_username: str = "admin"
    admin_password: str = "admin"


def get_settings() -> Settings:
    return Settings()
