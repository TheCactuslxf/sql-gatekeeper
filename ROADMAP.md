# Roadmap

SQL Gatekeeper is currently an early-stage project focused on one concrete production problem: safely handling LLM-generated MySQL queries for systems that use logical tables and physical shards.

## Near Term

- Improve README examples and add a terminal demo GIF.
- Publish the first tagged release, `v0.1.0`.
- Add GitHub issue templates and labels for bugs, features, docs, and good first issues.
- Replace the lightweight SQL parser with an AST-based parser such as `sqlglot`.
- Add more policy tests for tenant filters, table allowlists, and column deny lists.

## Mid Term

- Add MCP server mode so AI agents can discover and call SQL Gatekeeper as a tool.
- Publish a Docker image.
- Publish a PyPI package.
- Add a policy DSL for common database guardrails.
- Add a small audit dashboard for request history and rejected-query analysis.

## Longer Term

- Support PostgreSQL.
- Support multi-tenant policy profiles.
- Add OpenTelemetry metrics.
- Add pluggable secret providers for datasource credentials.
- Add benchmark datasets for LLM-generated SQL safety checks.

## Design Principles

- The gateway should fail closed.
- Safety checks should run after logical SQL has been rewritten to physical SQL.
- Route diagnostics should explain what the gateway needed, found, and rejected.
- Execution should use least-privilege, read-only datasource credentials.
- Auditing should record both allowed and rejected requests.
