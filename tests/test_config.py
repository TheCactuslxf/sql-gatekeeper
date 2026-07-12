from sql_gatekeeper.config import Settings


def test_meta_db_dsn_builds_from_settings():
    settings = Settings(
        META_DB_HOST="db.example.com",
        META_DB_PORT=3307,
        META_DB_NAME="meta",
        META_DB_USER="gatekeeper",
        META_DB_PASSWORD="secret",
    )

    assert settings.meta_db_dsn == "mysql+pymysql://gatekeeper:secret@db.example.com:3307/meta"


def test_demo_datasource_settings_can_be_overridden():
    settings = Settings(
        DEMO_USER_DB_HOST="biz-user-db",
        DEMO_USER_DB_PORT=3306,
        DEMO_ORDER_DB_HOST="biz-order-db",
        DEMO_ORDER_DB_PORT=3306,
    )

    assert settings.demo_user_db_host == "biz-user-db"
    assert settings.demo_user_db_port == 3306
    assert settings.demo_order_db_host == "biz-order-db"
    assert settings.demo_order_db_port == 3306

