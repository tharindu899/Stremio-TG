#!/usr/bin/env bash
set -e

export PORT="${PORT:-8000}"
printf '%s\n' "[startup] Launching Telegram-Stremio on port ${PORT}..."
exec python -m Backend
