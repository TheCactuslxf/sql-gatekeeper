from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.config import Settings, get_settings
from sql_gatekeeper.db.models import DatasourceInstance
from sql_gatekeeper.repositories.datasource import DatasourceInstanceRepository


READONLY_COMMANDS = {
    "GET",
    "MGET",
    "HGET",
    "HMGET",
    "HGETALL",
    "EXISTS",
    "TTL",
    "PTTL",
    "TYPE",
    "LLEN",
    "SCARD",
    "ZCARD",
    "LRANGE",
    "ZRANGE",
    "SMEMBERS",
}

DENIED_COMMANDS = {
    "SET",
    "MSET",
    "DEL",
    "UNLINK",
    "EXPIRE",
    "PEXPIRE",
    "PERSIST",
    "RENAME",
    "FLUSHDB",
    "FLUSHALL",
    "EVAL",
    "EVALSHA",
    "CONFIG",
    "KEYS",
    "SCAN",
    "HSET",
    "HMSET",
    "HDEL",
    "LPUSH",
    "RPUSH",
    "LPOP",
    "RPOP",
    "SADD",
    "SREM",
    "ZADD",
    "ZREM",
}


@dataclass(frozen=True)
class RedisDecision:
    allowed: bool
    reason_code: str
    message: str
    command: str
    args: list[str]
    datasource_code: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RedisExecuteResult:
    allowed: bool
    reason_code: str
    message: str
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: int


@dataclass(frozen=True)
class RedisRouteResolution:
    datasource: DatasourceInstance | None
    reason_code: str = ""
    message: str = ""


class RedisGatekeeperService:
    def __init__(self, settings: Settings | None = None, session: Session | None = None):
        self.settings = settings or get_settings()
        self.session = session

    def check(self, command: str, args: list[str], redis_context: dict[str, Any] | None = None) -> RedisDecision:
        normalized_command = command.strip().upper()
        normalized_args = [str(arg) for arg in args]
        redis_context = redis_context or {}

        if not normalized_command:
            return self._reject("EMPTY_REDIS_COMMAND", "Redis command must not be empty", normalized_command, normalized_args, "")

        if normalized_command in DENIED_COMMANDS:
            return self._reject(
                "REDIS_COMMAND_DENIED",
                f"Redis command '{normalized_command}' is not allowed",
                normalized_command,
                normalized_args,
                str(redis_context.get("datasource_code") or ""),
            )

        if normalized_command not in READONLY_COMMANDS:
            return self._reject(
                "REDIS_COMMAND_UNSUPPORTED",
                f"Redis command '{normalized_command}' is not supported by the safe Redis gatekeeper",
                normalized_command,
                normalized_args,
                str(redis_context.get("datasource_code") or ""),
            )

        arg_decision = self._validate_args(
            normalized_command,
            normalized_args,
            str(redis_context.get("datasource_code") or ""),
        )
        if arg_decision is not None:
            return arg_decision

        route = self._resolve_datasource(normalized_command, normalized_args, redis_context)
        datasource = route.datasource
        datasource_code = str(redis_context.get("datasource_code") or (datasource.datasource_code if datasource else ""))

        if datasource is None:
            return self._reject(route.reason_code, route.message, normalized_command, normalized_args, datasource_code)

        if datasource.db_type.lower() != "redis":
            return self._reject(
                "REDIS_DATASOURCE_TYPE_INVALID",
                f"Datasource '{datasource_code}' is not a Redis datasource",
                normalized_command,
                normalized_args,
                datasource_code,
            )

        key_decision = self._validate_keys(normalized_command, normalized_args, datasource)
        if key_decision is not None:
            return key_decision

        return RedisDecision(
            allowed=True,
            reason_code="ALLOW",
            message="Redis command passed readonly command, key scope, and result limit checks",
            command=normalized_command,
            args=normalized_args,
            datasource_code=datasource_code,
            diagnostics=[
                {
                    "datasource": {
                        "code": datasource.datasource_code,
                        "host": datasource.host,
                        "port": datasource.port,
                        "database": datasource.database_name,
                    },
                    "allowed_commands": sorted(READONLY_COMMANDS),
                    "max_keys_per_request": self.settings.redis_max_keys_per_request,
                    "max_result_items": self.settings.redis_max_result_items,
                    "allowed_key_prefixes": self._allowed_prefixes(datasource),
                    "route_context": {
                        "catlog_name": self._catalog_name(redis_context),
                    },
                }
            ],
        )

    def execute(self, decision: RedisDecision) -> RedisExecuteResult:
        if not decision.allowed:
            return RedisExecuteResult(False, decision.reason_code, decision.message, [], 0, 0)

        started_at = time.perf_counter()
        datasource = self._datasource(decision.datasource_code)
        if datasource is None:
            return RedisExecuteResult(
                False,
                "REDIS_DATASOURCE_NOT_FOUND",
                f"Redis datasource '{decision.datasource_code}' was not found",
                [],
                0,
                int((time.perf_counter() - started_at) * 1000),
            )
        client = self._client(datasource)
        preflight = self._preflight_result_size(client, decision)
        if preflight is not None:
            execution_ms = int((time.perf_counter() - started_at) * 1000)
            return RedisExecuteResult(False, preflight[0], preflight[1], [], 0, execution_ms)

        raw_result = self._run_command(client, decision.command, decision.args)
        rows = self._format_rows(decision.command, decision.args, raw_result)
        execution_ms = int((time.perf_counter() - started_at) * 1000)

        if len(rows) > self.settings.redis_max_result_items:
            return RedisExecuteResult(
                False,
                "REDIS_RESULT_LIMIT_EXCEEDED",
                f"Redis result returned {len(rows)} items, exceeding max {self.settings.redis_max_result_items}",
                [],
                0,
                execution_ms,
            )

        return RedisExecuteResult(
            True,
            "EXECUTED",
            "Redis command executed successfully",
            rows,
            len(rows),
            execution_ms,
        )

    def _client(self, datasource: DatasourceInstance):
        return redis.Redis(
            host=datasource.host,
            port=datasource.port,
            db=self._redis_db(datasource),
            password=self._resolve_password(datasource.password_secret_ref),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )

    def _datasource(self, datasource_code: str) -> DatasourceInstance | None:
        if self.session is not None:
            return DatasourceInstanceRepository(self.session).get_enabled_by_code(datasource_code)

        if datasource_code != self.settings.redis_datasource_code:
            return None

        return DatasourceInstance(
            datasource_code=self.settings.redis_datasource_code,
            display_name="Configured Redis",
            db_type="redis",
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            database_name=str(self.settings.redis_db),
            username="",
            password_secret_ref=f"local:{self.settings.redis_password}" if self.settings.redis_password else "",
            read_only=True,
            enabled=True,
            extra={},
        )

    def _resolve_datasource(
        self,
        command: str,
        args: list[str],
        redis_context: dict[str, Any],
    ) -> RedisRouteResolution:
        datasource_code = str(redis_context.get("datasource_code") or "")
        if datasource_code:
            datasource = self._datasource(datasource_code)
            if datasource is None:
                return RedisRouteResolution(
                    None,
                    "REDIS_DATASOURCE_NOT_FOUND",
                    f"Redis datasource '{datasource_code}' was not found",
                )
            return RedisRouteResolution(datasource)

        if self.session is None:
            datasource = self._datasource(self.settings.redis_datasource_code)
            if datasource is None:
                return RedisRouteResolution(
                    None,
                    "REDIS_DATASOURCE_NOT_FOUND",
                    f"Redis datasource '{self.settings.redis_datasource_code}' was not found",
                )
            return RedisRouteResolution(datasource)

        catalog_name = self._catalog_name(redis_context)
        if not catalog_name:
            return RedisRouteResolution(
                None,
                "REDIS_ROUTE_CONTEXT_REQUIRED",
                "Redis routing requires redis_context.catlog_name/catalog_name or redis_context.datasource_code",
            )

        key = self._key_args(command, args)[:1]
        route_key = key[0] if key else ""
        stmt = select(DatasourceInstance).where(
            DatasourceInstance.db_type == "redis",
            DatasourceInstance.enabled.is_(True),
        )
        candidates = list(self.session.execute(stmt).scalars())
        matching_catalog = [
            datasource
            for datasource in candidates
            if self._datasource_catalog(datasource).lower() == catalog_name.lower()
        ]
        if not matching_catalog:
            return RedisRouteResolution(
                None,
                "REDIS_ROUTE_NOT_FOUND",
                f"No Redis datasource matched catalog '{catalog_name}'",
            )
        matching_key = [
            datasource
            for datasource in matching_catalog
            if not route_key or self._key_allowed_by_datasource(route_key, datasource)
        ]
        if len(matching_key) == 1:
            return RedisRouteResolution(matching_key[0])
        if not matching_key:
            return RedisRouteResolution(
                None,
                "REDIS_ROUTE_NOT_FOUND",
                f"No Redis datasource matched catalog '{catalog_name}' and key '{route_key}'",
            )
        return RedisRouteResolution(
            None,
            "REDIS_ROUTE_AMBIGUOUS",
            f"Multiple Redis datasources matched catalog '{catalog_name}' and key '{route_key}'",
        )

    def _validate_args(self, command: str, args: list[str], datasource_code: str) -> RedisDecision | None:
        arg_count = len(args)
        if command in {"GET", "HGETALL", "TTL", "PTTL", "TYPE", "LLEN", "SCARD", "ZCARD", "SMEMBERS"} and arg_count != 1:
            return self._reject("REDIS_ARG_COUNT_INVALID", f"{command} requires exactly 1 argument", command, args, datasource_code)
        if command in {"HGET"} and arg_count != 2:
            return self._reject("REDIS_ARG_COUNT_INVALID", f"{command} requires exactly 2 arguments", command, args, datasource_code)
        if command in {"MGET", "EXISTS"} and not (1 <= arg_count <= self.settings.redis_max_keys_per_request):
            return self._reject(
                "REDIS_TOO_MANY_KEYS",
                f"{command} requires 1 to {self.settings.redis_max_keys_per_request} keys",
                command,
                args,
                datasource_code,
            )
        if command == "HMGET" and arg_count < 2:
            return self._reject("REDIS_ARG_COUNT_INVALID", "HMGET requires a key and at least one field", command, args, datasource_code)
        if command in {"LRANGE", "ZRANGE"} and arg_count != 3:
            return self._reject("REDIS_ARG_COUNT_INVALID", f"{command} requires key, start, and stop", command, args, datasource_code)
        if command in {"LRANGE", "ZRANGE"}:
            try:
                start = int(args[1])
                stop = int(args[2])
            except ValueError:
                return self._reject("REDIS_RANGE_INVALID", f"{command} start and stop must be integers", command, args, datasource_code)
            if start < 0 or stop < start:
                return self._reject("REDIS_RANGE_INVALID", f"{command} requires 0 <= start <= stop", command, args, datasource_code)
            if stop - start + 1 > self.settings.redis_max_result_items:
                return self._reject(
                    "REDIS_RANGE_LIMIT_EXCEEDED",
                    f"{command} range exceeds max {self.settings.redis_max_result_items} items",
                    command,
                    args,
                    datasource_code,
                )
        return None

    def _validate_keys(self, command: str, args: list[str], datasource: DatasourceInstance) -> RedisDecision | None:
        datasource_code = datasource.datasource_code
        prefixes = self._allowed_prefixes(datasource)
        for key in self._key_args(command, args):
            if not key:
                return self._reject("REDIS_KEY_EMPTY", "Redis key must not be empty", command, args, datasource_code)
            if len(key) > self.settings.redis_max_key_length:
                return self._reject(
                    "REDIS_KEY_TOO_LONG",
                    f"Redis key length exceeded max {self.settings.redis_max_key_length}",
                    command,
                    args,
                    datasource_code,
                )
            if any(token in key for token in ["*", "?", "["]):
                return self._reject("REDIS_KEY_PATTERN_DENIED", "Redis wildcard key patterns are not allowed", command, args, datasource_code)
            if prefixes and "*" not in prefixes and not any(key.startswith(prefix) for prefix in prefixes):
                return self._reject(
                    "REDIS_KEY_SCOPE_DENIED",
                    f"Redis key '{key}' is outside allowed prefixes",
                    command,
                    args,
                    datasource_code,
                )
        return None

    def _preflight_result_size(self, client, decision: RedisDecision) -> tuple[str, str] | None:
        key = decision.args[0]
        max_items = self.settings.redis_max_result_items
        if decision.command == "HGETALL" and int(client.hlen(key) or 0) > max_items:
            return "REDIS_RESULT_LIMIT_EXCEEDED", f"HGETALL result exceeds max {max_items} fields"
        if decision.command == "SMEMBERS" and int(client.scard(key) or 0) > max_items:
            return "REDIS_RESULT_LIMIT_EXCEEDED", f"SMEMBERS result exceeds max {max_items} members"
        return None

    def _run_command(self, client, command: str, args: list[str]):
        if command == "GET":
            return client.get(args[0])
        if command == "MGET":
            return client.mget(args)
        if command == "HGET":
            return client.hget(args[0], args[1])
        if command == "HMGET":
            return client.hmget(args[0], args[1:])
        if command == "HGETALL":
            return client.hgetall(args[0])
        if command == "EXISTS":
            return client.exists(*args)
        if command == "TTL":
            return client.ttl(args[0])
        if command == "PTTL":
            return client.pttl(args[0])
        if command == "TYPE":
            return client.type(args[0])
        if command == "LLEN":
            return client.llen(args[0])
        if command == "SCARD":
            return client.scard(args[0])
        if command == "ZCARD":
            return client.zcard(args[0])
        if command == "LRANGE":
            return client.lrange(args[0], int(args[1]), int(args[2]))
        if command == "ZRANGE":
            return client.zrange(args[0], int(args[1]), int(args[2]))
        if command == "SMEMBERS":
            return sorted(client.smembers(args[0]))
        raise ValueError(f"Unsupported Redis command: {command}")

    def _format_rows(self, command: str, args: list[str], result) -> list[dict[str, Any]]:
        if command == "MGET":
            return [{"key": key, "value": value} for key, value in zip(args, result)]
        if command == "HMGET":
            return [{"field": field, "value": value} for field, value in zip(args[1:], result)]
        if command == "HGETALL":
            return [{"field": field, "value": value} for field, value in sorted(result.items())]
        if command in {"LRANGE", "ZRANGE", "SMEMBERS"}:
            return [{"index": index, "value": value} for index, value in enumerate(result)]
        return [{"key": args[0] if args else "", "value": result}]

    def _key_args(self, command: str, args: list[str]) -> list[str]:
        if command in {"MGET", "EXISTS"}:
            return args
        if command == "HMGET":
            return args[:1]
        return args[:1]

    def _allowed_prefixes(self, datasource: DatasourceInstance | None = None) -> list[str]:
        if datasource is not None:
            raw_prefixes = datasource.extra.get("allowed_key_prefixes") if isinstance(datasource.extra, dict) else None
            if isinstance(raw_prefixes, list):
                return [str(item).strip() for item in raw_prefixes if str(item).strip()]
            if isinstance(raw_prefixes, str):
                return [item.strip() for item in raw_prefixes.split(",") if item.strip()]
        return [item.strip() for item in self.settings.redis_allowed_key_prefixes.split(",") if item.strip()]

    def _key_allowed_by_datasource(self, key: str, datasource: DatasourceInstance) -> bool:
        prefixes = self._allowed_prefixes(datasource)
        return not prefixes or "*" in prefixes or any(key.startswith(prefix) for prefix in prefixes)

    def _catalog_name(self, redis_context: dict[str, Any]) -> str:
        return str(
            redis_context.get("catlog_name")
            or redis_context.get("catalog_name")
            or redis_context.get("catalog")
            or ""
        )

    def _datasource_catalog(self, datasource: DatasourceInstance) -> str:
        if not isinstance(datasource.extra, dict):
            return ""
        return str(
            datasource.extra.get("catlog_name")
            or datasource.extra.get("catalog_name")
            or datasource.extra.get("redis_catalog")
            or ""
        )

    def _redis_db(self, datasource: DatasourceInstance) -> int:
        try:
            return int(datasource.database_name or 0)
        except ValueError:
            return 0

    def _resolve_password(self, secret_ref: str) -> str | None:
        if not secret_ref:
            return None
        if secret_ref.startswith("local:"):
            return secret_ref.split(":", 1)[1] or None
        return secret_ref

    def _reject(self, reason_code: str, message: str, command: str, args: list[str], datasource_code: str) -> RedisDecision:
        return RedisDecision(
            allowed=False,
            reason_code=reason_code,
            message=message,
            command=command,
            args=args,
            datasource_code=datasource_code,
            diagnostics=[],
        )
