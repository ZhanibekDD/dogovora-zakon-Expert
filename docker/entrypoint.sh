#!/bin/sh
set -e

case "$1" in
  migrate)
    exec alembic upgrade head
    ;;
  bot)
    exec python -m app.bot.main
    ;;
  api)
    exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
