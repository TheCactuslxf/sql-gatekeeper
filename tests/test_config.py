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

