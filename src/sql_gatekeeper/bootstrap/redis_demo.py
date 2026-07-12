from __future__ import annotations

import redis

from sql_gatekeeper.config import Settings, get_settings


def seed_demo_redis(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    client = redis.Redis(
        host=app_settings.redis_host,
        port=app_settings.redis_port,
        db=app_settings.redis_db,
        password=app_settings.redis_password or None,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
    )
    client.set("demo:user:10001", "bob")
    client.hset(
        "demo:user:10001:profile",
        mapping={
            "uid": "10001",
            "user_name": "bob",
            "status": "1",
        },
    )
    client.rpush("demo:recent_user_ids", "10000", "10001")


def main() -> None:
    seed_demo_redis()
    print("demo redis keys seeded")


if __name__ == "__main__":
    main()
