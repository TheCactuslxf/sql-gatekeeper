from sql_gatekeeper.config import Settings
from sql_gatekeeper.services.redis_gatekeeper import RedisDecision, RedisGatekeeperService


class FakeRedisClient:
    def __init__(self):
        self.values = {"demo:user:10001": "bob"}

    def get(self, key):
        return self.values.get(key)

    def hlen(self, key):
        return 0

    def scard(self, key):
        return 0


def _settings() -> Settings:
    return Settings(
        REDIS_ALLOWED_KEY_PREFIXES="demo:",
        REDIS_MAX_KEYS_PER_REQUEST=2,
        REDIS_MAX_RESULT_ITEMS=3,
    )


def test_redis_check_allows_readonly_get():
    decision = RedisGatekeeperService(_settings()).check("get", ["demo:user:10001"], {})

    assert decision.allowed is True
    assert decision.command == "GET"
    assert decision.datasource_code == "demo_redis"


def test_redis_check_rejects_write_command():
    decision = RedisGatekeeperService(_settings()).check("set", ["demo:user:10001", "bob"], {})

    assert decision.allowed is False
    assert decision.reason_code == "REDIS_COMMAND_DENIED"


def test_redis_check_rejects_wildcard_key():
    decision = RedisGatekeeperService(_settings()).check("get", ["demo:user:*"], {})

    assert decision.allowed is False
    assert decision.reason_code == "REDIS_KEY_PATTERN_DENIED"


def test_redis_check_rejects_key_outside_allowed_prefixes():
    decision = RedisGatekeeperService(_settings()).check("get", ["secret:user:10001"], {})

    assert decision.allowed is False
    assert decision.reason_code == "REDIS_KEY_SCOPE_DENIED"


def test_redis_check_rejects_range_above_limit():
    decision = RedisGatekeeperService(_settings()).check("lrange", ["demo:list", "0", "99"], {})

    assert decision.allowed is False
    assert decision.reason_code == "REDIS_RANGE_LIMIT_EXCEEDED"


def test_redis_execute_formats_get_result(monkeypatch):
    service = RedisGatekeeperService(_settings())
    monkeypatch.setattr(service, "_client", lambda: FakeRedisClient())
    decision = RedisDecision(
        allowed=True,
        reason_code="ALLOW",
        message="ok",
        command="GET",
        args=["demo:user:10001"],
        datasource_code="demo_redis",
    )

    result = service.execute(decision)

    assert result.allowed is True
    assert result.reason_code == "EXECUTED"
    assert result.rows == [{"key": "demo:user:10001", "value": "bob"}]
