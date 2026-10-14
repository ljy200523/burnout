from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Student Wellbeing API"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./burnout.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
