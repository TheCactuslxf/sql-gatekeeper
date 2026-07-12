# Security Policy

SQL Gatekeeper is a security-sensitive project because it validates and executes LLM-generated SQL.

## Supported Versions

The project is currently pre-1.0. Security fixes target the `main` branch until versioned releases are established.

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

Report security concerns by creating a private advisory on GitHub if available, or contact the maintainer through the GitHub profile linked from the repository.

Useful details include:

- The SQL input and route context.
- The expected decision.
- The actual decision.
- Whether the SQL was checked or executed.
- Any relevant metadata or policy configuration.

## Security Model

- Only `SELECT` SQL is supported in the current stage.
- Execution should use read-only datasource credentials.
- Safety checks run on rewritten physical SQL.
- Requests should be audited whether they are allowed or rejected.
- Unknown tables, missing route factors, and unsafe plans should fail closed.
