from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="sql-gatekeeper", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")

    meta_db_host: str = Field(default="127.0.0.1", alias="META_DB_HOST")
    meta_db_port: int = Field(default=33061, alias="META_DB_PORT")
    meta_db_name: str = Field(default="gatekeeper_meta", alias="META_DB_NAME")
    meta_db_user: str = Field(default="gatekeeper", alias="META_DB_USER")
    meta_db_password: str = Field(default="gatekeeper", alias="META_DB_PASSWORD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @property
    def meta_db_dsn(self) -> str:
        return (
            f"mysql+pymysql://{self.meta_db_user}:{self.meta_db_password}"
            f"@{self.meta_db_host}:{self.meta_db_port}/{self.meta_db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

