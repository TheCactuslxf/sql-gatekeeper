from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import redis

from sql_gatekeeper.config import Settings, get_settings


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


class RedisGatekeeperService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def check(self, command: str, args: list[str], redis_context: dict[str, Any] | None = None) -> RedisDecision:
        normalized_command = command.strip().upper()
        normalized_args = [str(arg) for arg in args]
        datasource_code = str((redis_context or {}).get("datasource_code") or self.settings.redis_datasource_code)

        if not normalized_command:
            return self._reject("EMPTY_REDIS_COMMAND", "Redis command must not be empty", normalized_command, normalized_args, datasource_code)

        if normalized_command in DENIED_COMMANDS:
            return self._reject(
                "REDIS_COMMAND_DENIED",
                f"Redis command '{normalized_command}' is not allowed",
                normalized_command,
                normalized_args,
                datasource_code,
            )

        if normalized_command not in READONLY_COMMANDS:
            return self._reject(
                "REDIS_COMMAND_UNSUPPORTED",
                f"Redis command '{normalized_command}' is not supported by the safe Redis gatekeeper",
                normalized_command,
                normalized_args,
                datasource_code,
            )

        arg_decision = self._validate_args(normalized_command, normalized_args, datasource_code)
        if arg_decision is not None:
            return arg_decision

        key_decision = self._validate_keys(normalized_command, normalized_args, datasource_code)
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
                    "allowed_commands": sorted(READONLY_COMMANDS),
                    "max_keys_per_request": self.settings.redis_max_keys_per_request,
                    "max_result_items": self.settings.redis_max_result_items,
                    "allowed_key_prefixes": self._allowed_prefixes(),
                }
            ],
        )

    def execute(self, decision: RedisDecision) -> RedisExecuteResult:
        if not decision.allowed:
            return RedisExecuteResult(False, decision.reason_code, decision.message, [], 0, 0)

        started_at = time.perf_counter()
        client = self._client()
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

    def _client(self):
        return redis.Redis(
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            db=self.settings.redis_db,
            password=self.settings.redis_password or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
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

    def _validate_keys(self, command: str, args: list[str], datasource_code: str) -> RedisDecision | None:
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
            prefixes = self._allowed_prefixes()
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

    def _allowed_prefixes(self) -> list[str]:
        return [item.strip() for item in self.settings.redis_allowed_key_prefixes.split(",") if item.strip()]

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
