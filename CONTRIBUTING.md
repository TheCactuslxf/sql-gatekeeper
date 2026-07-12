# Contributing

Thanks for taking a look at SQL Gatekeeper. The project is early, so clear bug reports, focused tests, and small pull requests are especially valuable.

## Development Setup

```bash
git clone https://github.com/TheCactuslxf/sql-gatekeeper.git
cd sql-gatekeeper
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run unit tests:

```bash
pytest tests
```

Run Docker-backed MySQL tests:

```bash
docker compose up -d
RUN_DOCKER_TESTS=1 pytest tests
docker compose down -v
```

## Pull Request Guidelines

- Keep changes focused on one behavior or documentation improvement.
- Add or update tests for behavior changes.
- Prefer small, composable modules that match the current package structure.
- Keep safety checks fail-closed.
- Include a short explanation of user-visible behavior in the PR description.

## Good First Contributions

- Improve examples and documentation.
- Add more rejected-query test cases.
- Add route diagnostics examples.
- Add CI improvements.
- Add parser coverage for common SQL forms.
