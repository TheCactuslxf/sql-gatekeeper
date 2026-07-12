#!/usr/bin/env sh
set -eu

python -m sql_gatekeeper.bootstrap.meta

exec "$@"
