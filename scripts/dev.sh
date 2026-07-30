#!/bin/sh

set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing .venv. Create it with Python 3.11+ and install backend/requirements.txt."
  exit 1
fi

stop_servers() {
  kill "$api_pid" "$frontend_pid" 2>/dev/null || true
}

trap stop_servers EXIT INT TERM

.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
api_pid=$!

.venv/bin/python -m http.server 5501 --directory frontend --bind 127.0.0.1 &
frontend_pid=$!

echo "APSE frontend: http://127.0.0.1:5501"
echo "APSE API docs: http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop both servers."

wait
