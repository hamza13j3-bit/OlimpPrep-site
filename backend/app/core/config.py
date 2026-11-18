from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret-change-me-please-use-32+-bytes"
    admin_email: str = ""
    database_url: str = "sqlite:///./olimpprep.db"
    access_token_minutes: int = 60 * 24


settings = Settings()
