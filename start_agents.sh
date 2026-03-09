#!/bin/bash
# Start all A2A agents + Root agent + Live server
# Usage: bash start_agents.sh
# Stop:  Ctrl+C (kills all background processes)

cd "$(dirname "$0")"

trap 'echo "Stopping all agents..."; kill $(jobs -p) 2>/dev/null; wait; echo "All stopped."; exit 0' INT TERM

echo "Starting sub-agents..."

python -m uvicorn agents.adk.caclub_a2a.agent:a2a_app --host 127.0.0.1 --port 8001 &
python -m uvicorn agents.adk.taxtmi_a2a.agent:a2a_app --host 127.0.0.1 --port 8002 &
python -m uvicorn agents.adk.turbotax_a2a.agent:a2a_app --host 127.0.0.1 --port 8003 &
python -m uvicorn agents.adk.taxprofblog_a2a.agent:a2a_app --host 127.0.0.1 --port 8004 &

sleep 3
echo "Starting root agent..."

python -m uvicorn agents.adk.root_agent.agent:a2a_app --host 127.0.0.1 --port 8000 &

sleep 2
echo "Starting graph API and live server..."

python -m uvicorn graph_api:app --host 127.0.0.1 --port 9000 &
python -m uvicorn live.server:app --host 0.0.0.0 --port 8080 &

echo ""
echo "All agents running:"
echo "  8001 - CAClub"
echo "  8002 - TaxTMI"
echo "  8003 - TurboTax"
echo "  8004 - TaxProfBlog"
echo "  8000 - Root Agent"
echo "  9000 - Graph API"
echo "  8080 - Live Server"
echo ""
echo "Press Ctrl+C to stop all"

wait
