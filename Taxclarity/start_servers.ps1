# TaxAgent — Windows Backend Startup Script
# Starts all A2A agents and support servers in separate PowerShell windows.
# Run from the TaxAgent root with the .venv activated:
#   .\.venv\Scripts\Activate.ps1
#   .\start_servers.ps1

$Root = $PSScriptRoot

# Resolve python from the venv
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Virtual env not found at $Python. Activate it first."
    exit 1
}

# Load .env so GOOGLE_API_KEY etc. are available in each child window
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | Where-Object { $_ -match "^\s*[^#]" } | ForEach-Object {
        $parts = $_ -split "=", 2
        if ($parts.Length -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

$Servers = @(
    @{ Name = "Root Agent     :8000"; Args = "agents.adk.root_agent.agent:a2a_app --port 8000" },
    @{ Name = "CAClubIndia    :8001"; Args = "agents.adk.caclub_a2a.agent:a2a_app --port 8001" },
    @{ Name = "TaxTMI         :8002"; Args = "agents.adk.taxtmi_a2a.agent:a2a_app --port 8002" },
    @{ Name = "WebSocket      :8003"; Args = "backend.websocket_server:app --port 8003" },
    @{ Name = "TaxProfBlog    :8004"; Args = "agents.adk.taxprofblog_a2a.agent:a2a_app --port 8004" },
    @{ Name = "TurboTax       :8005"; Args = "agents.adk.turbotax_a2a.agent:a2a_app --port 8005" },
    @{ Name = "Graph API      :8006"; Args = "backend.graph_api:app --port 8006" }
)

Write-Host "Starting TaxAgent backend servers..." -ForegroundColor Cyan
Write-Host ""

foreach ($s in $Servers) {
    $Cmd = "Set-Location '$Root'; & '$Python' -m uvicorn $($s.Args)"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $Cmd -WindowStyle Normal
    Write-Host "  ✓ $($s.Name)" -ForegroundColor Green
    Start-Sleep -Milliseconds 400   # slight stagger to avoid port collisions
}

Write-Host ""
Write-Host "All servers starting in separate windows." -ForegroundColor Cyan
Write-Host "Frontend: cd frontend-next && npm run dev" -ForegroundColor Yellow
