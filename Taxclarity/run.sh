#!/bin/bash

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PIDFILE="$ROOT/.pids"
PORTS=(8000 8001 8002 8003 8004 8005 8006)

if [ ! -f "$PYTHON" ]; then
    echo "ERROR: .venv not found."
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

if [ -f "$PIDFILE" ]; then
    echo "PID file already exists at $PIDFILE"
    echo "If servers are already running, run ./stop.sh first."
    exit 1
fi

: > "$PIDFILE"

if command -v lsof >/dev/null 2>&1; then
    in_use=0
    for port in "${PORTS[@]}"; do
        pids="$(lsof -ti :$port 2>/dev/null)"
        if [ -n "$pids" ]; then
            echo "Port $port is already in use (pid(s): $pids)."
            in_use=1
        fi
    done
    if [ "$in_use" -eq 1 ]; then
        echo "Stop existing servers first: ./stop.sh"
        rm -f "$PIDFILE"
        exit 1
    fi
else
    echo "Warning: lsof not found; skipping port checks."
fi

run_server_bg() {
    TITLE=$1
    PORT=$2
    MODULE=$3

    "$PYTHON" -m uvicorn $MODULE --port $PORT --log-level info &
    echo $! >> "$PIDFILE"
}

echo ""
echo "████████╗ █████╗ ██╗  ██╗ ██████╗██╗      █████╗ ██████╗ ██╗████████╗██╗   ██╗"
echo "   ██╔══╝██╔══██╗╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗██║╚══██╔══╝╚██╗ ██╔╝"
echo "   ██║   ███████║ ╚███╔╝ ██║     ██║     ███████║██████╔╝██║   ██║    ╚████╔╝"
echo "   ██║   ██╔══██║ ██╔██╗ ██║     ██║     ██╔══██║██╔══██╗██║   ██║     ╚██╔╝"
echo "   ██║   ██║  ██║██╔╝ ██╗╚██████╗███████╗██║  ██║██║  ██║██║   ██║      ██║"
echo "   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝   ╚═╝      ╚═╝"
echo ""

echo ""
echo "Starting backend servers..."
echo ""

echo "Starting WebSocket Server → http://localhost:8003"
run_server_bg "WebSocket Server" 8003 "backend.websocket_server:app"
echo "Starting Root Agent → http://localhost:8000"
run_server_bg "Root Agent" 8000 "agents.adk.root_agent.agent:a2a_app"
echo "Starting CAClubIndia Agent → http://localhost:8001"
run_server_bg "CAClubIndia Agent" 8001 "agents.adk.caclub_a2a.agent:a2a_app"
echo "Starting TaxTMI Agent → http://localhost:8002"
run_server_bg "TaxTMI Agent" 8002 "agents.adk.taxtmi_a2a.agent:a2a_app"
echo "Starting TaxProfBlog Agent → http://localhost:8004"
run_server_bg "TaxProfBlog Agent" 8004 "agents.adk.taxprofblog_a2a.agent:a2a_app"
echo "Starting TurboTax Agent → http://localhost:8005"
run_server_bg "TurboTax Agent" 8005 "agents.adk.turbotax_a2a.agent:a2a_app"
echo "Starting Graph API → http://localhost:8006"
run_server_bg "Graph API" 8006 "backend.graph_api:app"

echo ""
echo ""
echo "Backend servers started."
echo "Start frontend separately with: cd \"$ROOT/frontend\" && npm run dev"
echo "Run ./stop.sh to stop all backend servers."
