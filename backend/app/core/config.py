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

    anthropic_api_key: str = ""
    tradingagents_path: str = "/opt/tradingagents"
    tradingagents_venv_python: str = "/opt/tradingagents/.venv/bin/python"
    tradingagents_results_dir: str = "/opt/tradingagents/data"

    # ["../.env", ".env"]: root .env for local dev (run from backend/); Docker injects env vars directly so neither file needs to exist
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], env_file_encoding="utf-8")


settings = Settings()
