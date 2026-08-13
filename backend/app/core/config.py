from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    api_key: str = ""
    cors_origins: str = "http://localhost:3000"

    pushover_api_token: str = ""
    pushover_user_key: str = ""

    gmail_user: str = ""
    gmail_app_password: str = ""

    notify_pushover: bool = True
    notify_email: bool = False

    finnhub_api_key: str = ""

    synology_host: str = ""
    synology_port: int = 5001
    synology_use_https: bool = True
    synology_user: str = ""
    synology_password: str = ""
    # NAS lives on LAN with DSM's default self-signed cert; flip to True if a valid cert is configured
    synology_verify_ssl: bool = False

    anthropic_api_key: str = ""
    tradingagents_path: str = "/opt/tradingagents"
    tradingagents_venv_python: str = "/opt/tradingagents/.venv/bin/python"
    tradingagents_results_dir: str = "/opt/tradingagents/data"
    tradingagents_idle_timeout_seconds: int = 600
    tradingagents_hard_cap_seconds: int = 7200

    # ["../.env", ".env"]: root .env for local dev (run from backend/); Docker injects env vars directly so neither file needs to exist
    # extra="ignore": root .env is shared across backend/frontend/pihole — vars meant for other
    # services (e.g. PIHOLE_WEBPASSWORD) shouldn't fail Settings validation
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], env_file_encoding="utf-8", extra="ignore")


settings = Settings()
