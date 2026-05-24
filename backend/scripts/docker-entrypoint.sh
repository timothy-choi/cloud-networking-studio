#!/bin/sh
set -eu

cd /app

echo "Running Alembic migrations..."
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
