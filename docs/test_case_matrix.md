# SQL Gatekeeper Test Case Matrix

## Purpose

This file summarizes the current test coverage so the repository can be published with a clear verification baseline.

## Coverage Matrix

| Area | Scenario | Expected Result | Test Reference |
| --- | --- | --- | --- |
| SQL parser | Parse basic `SELECT` and predicates | SQL structure can be extracted correctly | `tests/test_sql_parser.py` |
| SQL parser | Reject unsupported or malformed input | Request is blocked before execution | `tests/test_sql_parser.py` |
| Precheck | Reject non-`SELECT` SQL | Dangerous write SQL is blocked | `tests/test_precheck.py` |
| Precheck | Enforce `LIMIT` | Missing or excessive `LIMIT` is blocked | `tests/test_precheck.py` |
| Routing | SQL already contains physical shard table | Direct physical table access is recognized only if registered | `tests/test_routing.py` |
| Routing | Logical table `user` rewritten by uid modulo | `user` is routed to `user_0` or `user_1` | `tests/test_routing.py`, `tests/test_sql_rewrite.py` |
| Routing | Logical table `order` rewritten by route context | `order` is routed to month shard such as `order_2025_07` | `tests/test_routing.py`, `tests/test_sql_rewrite.py` |
| Routing | Combined SQL predicate and route context | Multi-factor routing resolves the target shard | `tests/test_routing.py` |
| Routing | Missing route context | Request is rejected before execution | `tests/test_routing.py`, `tests/test_api.py`, `tests/test_http_api_e2e.py` |
| Routing | Dynamic shard alias usage | Aliased SQL is still rewritten to the right shard | `tests/test_routing.py`, `tests/test_api.py` |
| Filter chain | Small table without index risk | Request is allowed | `tests/test_filter_chain.py` |
| Filter chain | Missing `LIMIT` or over-limit | Request is rejected by policy | `tests/test_filter_chain.py` |
| Explain | `EXPLAIN` captures scan risk | Large scan / full scan is rejected | `tests/test_explain_mysql.py` |
| Explain | `Using temporary` / `Using filesort` risk | Risky execution plan is rejected | `tests/test_explain_mysql.py` |
| Large table | 1,000,000-row shard without selective plan | Query is rejected on large-table policy | `tests/test_execute_mysql.py`, `tests/test_http_api_e2e.py` |
| Large table | 1,000,000-row shard with safe point lookup | Query is allowed | `tests/test_execute_mysql.py`, `tests/test_http_api_e2e.py` |
| Audit | Approved request writes audit log | `request_audit_log` contains real request record | `tests/test_audit.py`, `tests/test_http_api_e2e.py` |
| Audit | Rejected request writes audit log | Blocked request is also recorded | `tests/test_audit.py`, `tests/test_http_api_e2e.py` |
| Bootstrap | Metadata schema creation | Metadata tables are created in MySQL | `tests/test_bootstrap_mysql.py` |
| Bootstrap | Seed data load | Base datasource / policy / route metadata exists | `tests/test_bootstrap_mysql.py`, `tests/test_bootstrap_unit.py` |
| HTTP API | `/check-sql` returns allow decision | End-to-end request succeeds through HTTP | `tests/test_api.py`, `tests/test_http_api_e2e.py` |
| HTTP API | `/check-sql` returns reject decision | End-to-end request is blocked through HTTP | `tests/test_api.py`, `tests/test_http_api_e2e.py` |

## Notes

- Business shard table data is intentionally excluded from repository seed scripts.
- Metadata seed data should be versioned because routing, policy, and datasource definitions are part of system behavior.
- `table_stats_snapshot` and `request_audit_log` should not have static initialization rows.
