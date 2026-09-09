from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WMS Order Lifecycle Simulator"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///:memory:"
    database_echo: bool = False
    database_auto_create_tables: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WMS_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
