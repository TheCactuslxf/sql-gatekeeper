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

    demo_user_db_host: str = Field(default="127.0.0.1", alias="DEMO_USER_DB_HOST")
    demo_user_db_port: int = Field(default=33062, alias="DEMO_USER_DB_PORT")
    demo_user_db_name: str = Field(default="biz_user", alias="DEMO_USER_DB_NAME")
    demo_user_db_user: str = Field(default="readonly", alias="DEMO_USER_DB_USER")
    demo_user_db_password: str = Field(default="readonly", alias="DEMO_USER_DB_PASSWORD")

    demo_order_db_host: str = Field(default="127.0.0.1", alias="DEMO_ORDER_DB_HOST")
    demo_order_db_port: int = Field(default=33063, alias="DEMO_ORDER_DB_PORT")
    demo_order_db_name: str = Field(default="biz_order", alias="DEMO_ORDER_DB_NAME")
    demo_order_db_user: str = Field(default="readonly", alias="DEMO_ORDER_DB_USER")
    demo_order_db_password: str = Field(default="readonly", alias="DEMO_ORDER_DB_PASSWORD")

    redis_host: str = Field(default="127.0.0.1", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")
    redis_datasource_code: str = Field(default="demo_redis", alias="REDIS_DATASOURCE_CODE")
    redis_allowed_key_prefixes: str = Field(default="demo:,user:,order:", alias="REDIS_ALLOWED_KEY_PREFIXES")
    redis_max_keys_per_request: int = Field(default=20, alias="REDIS_MAX_KEYS_PER_REQUEST")
    redis_max_result_items: int = Field(default=100, alias="REDIS_MAX_RESULT_ITEMS")
    redis_max_key_length: int = Field(default=256, alias="REDIS_MAX_KEY_LENGTH")

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

