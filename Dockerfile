FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY docker/app-entrypoint.sh /usr/local/bin/sql-gatekeeper-entrypoint

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chmod +x /usr/local/bin/sql-gatekeeper-entrypoint

EXPOSE 8080

ENTRYPOINT ["sql-gatekeeper-entrypoint"]
CMD ["uvicorn", "sql_gatekeeper.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
