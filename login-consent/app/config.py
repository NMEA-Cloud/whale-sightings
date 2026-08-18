from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hydra_admin_url: str = "https://hydra:4445"
    # step-ca's CA root, copied into certs/ by scripts/setup-tls.sh — lets httpx trust
    # Hydra's step-ca-issued cert on the admin API without disabling verification.
    hydra_admin_ca_bundle_path: str = "/certs/rootCA.pem"
    admin_username: str = "admin"
    admin_password: str = "admin"
    # How long Hydra remembers a successful login before requiring the form again — during
    # this window, clicking a delete action after a token expires/reload skips straight past
    # the login form (Hydra returns skip: true) instead of showing it. Shorten this for
    # demos where you want the form to reliably reappear; see the README's OAuth2 section
    # for how to also force it immediately without waiting.
    login_remember_seconds: int = 3600


def get_settings() -> Settings:
    return Settings()
