# Changelog

All notable changes to SQL Gatekeeper will be documented in this file.

## Unreleased

- Reworked project README for public open-source discovery.
- Added Chinese README.
- Added roadmap, contribution guide, security policy, and CI workflow.
- Added Dockerfile, one-command Docker Compose startup, and demo scripts.
- Added README demo screenshot.
- Added safe Redis check/execute API with readonly command allowlist and key-scope limits.
- Added metadata-backed Redis datasource selection via `redis_context.datasource_code`.

## 0.1.0

- Initial FastAPI service for checking and executing LLM-generated MySQL SQL.
- Logical-table to physical-table routing.
- SQL rewrite engine.
- Policy filter chain.
- EXPLAIN-based risk evaluation.
- Read-only execution path.
- Request audit logging.
- Docker Compose development environment with MySQL metadata and business databases.
