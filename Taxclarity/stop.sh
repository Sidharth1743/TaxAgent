#!/bin/bash

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$ROOT/.pids"

if [ ! -f "$PIDFILE" ]; then
  echo "No PID file found at $PIDFILE"
  echo "Trying to stop by ports (3000, 8000-8006)..."

  if ! command -v lsof >/dev/null 2>&1; then
    echo "lsof not found. Install it or stop processes manually."
    exit 1
  fi

  for port in 3000 8000 8001 8002 8003 8004 8005 8006; do
    pids="$(lsof -ti :$port 2>/dev/null)"
    if [ -n "$pids" ]; then
      echo "Stopping port $port (pid(s): $pids)"
      kill $pids 2>/dev/null || true
    fi
  done

  echo "Done."
  exit 0
fi

while read -r pid; do
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
done < "$PIDFILE"

rm -f "$PIDFILE"

if command -v lsof >/dev/null 2>&1; then
  for port in 3000 3001 8000 8001 8002 8003 8004 8005 8006; do
    pids="$(lsof -ti :$port 2>/dev/null)"
    if [ -n "$pids" ]; then
      kill $pids 2>/dev/null || true
    fi
  done
fi

echo "Stopped all servers."
