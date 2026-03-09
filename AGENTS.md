# Repository Guidelines

## Project Structure

```
TaxAgent/
├── main.py                        # CLI entry point (serve, graph-api, scrape)
├── graph_api.py                   # Knowledge graph REST API (:9000)
├── Dockerfile                     # Container build
├── docker-compose.yml             # Local dev compose (single container, all services)
├── supervisor.conf                # Process manager for all 7 services
├── requirements.txt               # Runtime dependencies
├── pyproject.toml                 # Project metadata
│
├── agents/                        # Scraper implementations + ADK agents
│   ├── caclub_agent.py            # CAClubIndia scraper
│   ├── taxtmi_agent.py            # TaxTMI scraper
│   ├── turbotax_agent.py          # TurboTax scraper
│   ├── taxprofblog_agent.py       # TaxProfBlog scraper
│   └── adk/                       # Google ADK A2A agent wrappers
│       ├── root_agent/            # Orchestrator (:8000) — tools, memory, response
│       ├── caclub_a2a/            # :8001
│       ├── taxtmi_a2a/            # :8002
│       ├── turbotax_a2a/          # :8003
│       ├── taxprofblog_a2a/       # :8004
│       └── cache.py               # File-based caching (SHA256 + TTL)
│
├── live/                          # Gemini Live voice server
│   ├── server.py                  # FastAPI: WebSocket bridge, static files, API proxies (:8080)
│   ├── tools.py                   # Function declarations + execution bridge to ADK agents
│   └── audio_utils.py             # PCM encode/decode, RMS computation
│
├── frontend/                      # Three-panel SPA (voice orb + chat + graph + sources)
│   ├── index.html                 # Deep-space themed layout
│   ├── styles.css                 # Sci-fi theme, orb animations, glassmorphic cards
│   ├── app.js                     # WebSocket audio client, UI orchestration, particles
│   └── components/
│       ├── voice-orb.js           # WebGL shader orb (OGL) with voice reactivity
│       ├── chat-panel.js          # Chat transcript with citation chips
│       ├── graph-panel.js         # D3.js force-directed knowledge graph
│       ├── source-cards.js        # Evidence cards with source logos
│       └── doc-scanner.js         # Camera/file upload for tax documents
│
├── memory/                        # Spanner property graph memory
│   ├── spanner_graph.py           # Schema (9 tables, 10 edge types), read/write ops
│   └── extractor.py               # Gemini-based structured extraction with retry
│
├── scraping/                      # Scraping utilities + legal scrapers
│   ├── utils.py                   # fetch_with_fallbacks(), is_blocked(), page_text()
│   ├── taxkanoon.py               # Indian Kanoon search + section scraper
│   └── casemine.py                # Casemine judgements scraper (JSON API + HTML fallback)
│
├── config/                        # Configuration
│   └── logging.py                 # Structured JSON logging (LOG_LEVEL env var)
│
├── scripts/                       # Utility scripts
│   ├── start_servers.sh           # Launch all 5 A2A servers on ports 8000-8004
│   └── spanner_init.py            # Initialize Spanner database schema
│
├── static/                        # Legacy graph UI
│   └── graph.html                 # Standalone Cytoscape.js graph viewer
│
└── data/                          # Cache files, scraper output (gitignored)
```

## How to Run

### Prerequisites
- Python 3.11+
- A `.env` file (copy from `.env.example` and fill in your keys)

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run Everything (3 terminals)

**Terminal 1** — A2A agents (ports 8000-8004):
```bash
source .venv/bin/activate
bash scripts/start_servers.sh
```

**Terminal 2** — Graph API (port 9000):
```bash
source .venv/bin/activate
python main.py graph-api
```

**Terminal 3** — Live server + frontend (port 8080):
```bash
source .venv/bin/activate
python -m uvicorn live.server:app --host 0.0.0.0 --port 8080 --reload
```

Then open **http://localhost:8080** in your browser.

### Run with Docker (single command)
```bash
docker compose up --build
```
All 7 services start in one container via supervisor. Open **http://localhost:8080**.

### Run Individual Scrapers
```bash
python main.py scrape caclub --query "tax on hackathon"
python main.py scrape taxkanoon --query "section 80c doctypes:laws"
python main.py scrape casemine --query "income from other source"
```

### Cloud Run Deployment
```bash
gcloud run deploy taxclarity \
  --source . \
  --region us-central1 \
  --memory 2Gi --cpu 2 \
  --min-instances 1 \
  --timeout 300 \
  --set-env-vars "GOOGLE_API_KEY=...,SPANNER_PROJECT_ID=...,SPANNER_INSTANCE_ID=...,SPANNER_DATABASE_ID=..."
```

## Environment Variables

All variables go in a local `.env` file (see `.env.example`).

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key (required) |
| `SPANNER_PROJECT_ID` / `SPANNER_INSTANCE_ID` / `SPANNER_DATABASE_ID` | Spanner graph DB connection |
| `GEMINI_LIVE_MODEL` | Live API model (default: `gemini-2.5-flash-native-audio-preview-12-2025`) |
| `LIVE_SERVER_PORT` | Live server port (default: 8080) |
| `ROOT_AGENT_URL` | Root agent URL (default: `http://localhost:8000`) |
| `GRAPH_API_URL` | Graph API URL (default: `http://localhost:9000`) |
| `CLUDO_CUSTOMER_ID` / `CLUDO_ENGINE_ID` / `CLUDO_SITE_KEY` / `CLUDO_API_URL` | TurboTax Cludo search API |
| `CASEMINE_COOKIE` | Casemine auth cookie (or use `data/casemine_cookies.txt`) |
| `SCRAPER_TIMEOUT_MS` | Stealth fetcher timeout in ms (default: 30000) |
| `LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO) |
| `CACHE_TTL_SECONDS` | A2A sub-agent cache TTL (default: 600) |

## Architecture

```
Browser (http://localhost:8080)
  ↕ WebSocket (audio PCM + JSON)
Live Server (live/server.py :8080)
  ↕ Gemini Live API (gemini-2.5-flash-native-audio-preview)
  ↕ Function Calls → Tool Bridge (live/tools.py)
      ↓
  ADK Root Agent (:8000)
    ├─ CAClub A2A (:8001)
    ├─ TaxTMI A2A (:8002)
    ├─ TurboTax A2A (:8003)
    └─ TaxProfBlog A2A (:8004)
      ↓
  Spanner Graph ←→ memory_tools
  Legal Enrichment ←→ Indian Kanoon + Casemine
```

- **Gemini Live** handles real-time voice conversation with function calling
- **ADK Root Agent** orchestrates 4 scraper sub-agents via A2A protocol
- **Legal Enrichment** fetches Indian Kanoon statutes + Casemine judgements
- **Spanner Graph** stores user profiles, queries, concepts, entities, resolutions (9 node tables, 10 edge types)
- **Frontend** is a three-panel SPA: knowledge graph (D3.js) | voice orb (WebGL) + chat | source evidence cards

## Coding Style
- Python: PEP 8, 4-space indentation, `snake_case` functions, `PascalCase` classes
- Use `logging` module (not `print()`). Import `config.logging.setup_logging()` at entry points
- Frontend: vanilla JS modules, no build step, CDN dependencies (Tailwind, D3, OGL)

## Commit Convention
`feat: ...`, `fix: ...`, `chore: ...` (Conventional Commits)

## Security
- Never commit secrets. Keep API keys in `.env` (gitignored)
- `.adk/` and `data/` are generated (gitignored)
