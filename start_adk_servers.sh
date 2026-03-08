#!/usr/bin/env bash
set -euo pipefail

# Start A2A servers for CAClubIndia, TaxTMI, TurboTax, TaxProfBlog, and Root agent.
# Usage: ./start_adk_servers.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONUNBUFFERED=1

cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  # Load .env variables (e.g., GOOGLE_API_KEY)
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

echo "Starting CAClubIndia A2A agent on :8001"
uvicorn agents.adk.caclub_a2a.agent:a2a_app --port 8001 &
PID1=$!

echo "Starting TaxTMI A2A agent on :8002"
uvicorn agents.adk.taxtmi_a2a.agent:a2a_app --port 8002 &
PID2=$!

echo "Starting TurboTax A2A agent on :8003"
uvicorn agents.adk.turbotax_a2a.agent:a2a_app --port 8003 &
PID3=$!

echo "Starting TaxProfBlog A2A agent on :8004"
uvicorn agents.adk.taxprofblog_a2a.agent:a2a_app --port 8004 &
PID4=$!

echo "Starting Root A2A agent on :8000"
uvicorn agents.adk.root_agent.agent:a2a_app --port 8000 &
PID5=$!

echo "PIDs: caclub=$PID1 taxtmi=$PID2 turbotax=$PID3 taxprofblog=$PID4 root=$PID5"
echo "Press Ctrl+C to stop all servers."

trap 'kill $PID1 $PID2 $PID3 $PID4 $PID5' INT TERM
wait $PID1 $PID2 $PID3 $PID4 $PID5
