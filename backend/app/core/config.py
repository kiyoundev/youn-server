from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    api_key: str = ""
    cors_origins: str = "http://localhost:3000"

    pushover_app_token: str = ""
    pushover_user_key: str = ""

    gmail_user: str = ""
    gmail_app_password: str = ""

    finnhub_api_key: str = ""

    # ["../.env", ".env"]: root .env for local dev (run from backend/); Docker injects env vars directly so neither file needs to exist
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], env_file_encoding="utf-8")


settings = Settings()
