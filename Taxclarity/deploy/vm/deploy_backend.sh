#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/saulgoodman/repo}"
BACKEND_ROOT="$APP_ROOT/Taxclarity"
VENV_PATH="${VENV_PATH:-/opt/saulgoodman/venv}"
BRANCH="${BRANCH:-main}"

cd "$APP_ROOT"
git fetch --all --prune
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -x "$VENV_PATH/bin/python" ]; then
  python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r "$BACKEND_ROOT/requirements.txt"

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart saulgoodman-backend
else
  cd "$BACKEND_ROOT"
  ./stop.sh || true
  VENV_PATH="$VENV_PATH" ./run.sh
fi
