# TaxClarity — Multi-Agent Tax Advisory System

TaxClarity is an AI-powered tax advisory system that aggregates evidence from multiple Indian and US tax knowledge sources, enriches answers with legal citations from court judgements and statutes, and maintains a persistent memory of each user's tax profile. It is built on **Google ADK** (Agent Development Kit) with the **A2A** (Agent-to-Agent) protocol, backed by **Gemini** as the LLM backbone and uses **Google genai SDK** for real-time voice interactions.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Getting Started](#getting-started)
4. [Environment Variables](#environment-variables)
5. [Services](#services)
6. [Memory System](#memory-system)
7. [Scraping Pipeline](#scraping-pipeline)
8. [Deployment](#deployment)

---

## Architecture

```
                                    +-------------------+
                                    |   Browser Client  |
                                    |  (Next.js SPA)    |
                                    +--------+----------+
                                             |
                                    WebSocket (PCM audio + JSON)
                                             |
                                    +--------v----------+
                                    |  WebSocket Server |
                                    |     :8003         |
                                    +--------+----------+
                                             |
                            +----------------+----------------+
                            |                 |                |
                    Gemini Live SDK    Function Calls      Tool Bridge
                    (google-genai)           |                |
                            |                 v                v
                            v          +-------+------+  +------v-------+
                   +--------+----+     | Memory Tools |  | Legal Enrich |
                   | Root Agent |     | (SQL+Vertex) |  | (Kanoon/Casemine)
                   |   :8000    |     +-------------+  +--------------+
                   +----+----+----+
                        |    |    |
           +------------+    |    +------------+
           |                 |                 |
           v                 v                 v
    +------+------+   +------+------+   +------+--------+
    | CAClub     |   | TaxTMI    |   | TurboTax     |
    | :8001      |   | :8002     |   | :8005        |
    +------+------+   +------+------+   +------+--------+
           |                 |                 |
           v                 v                 v
    +------+------+   +------+------+   +------+--------+
    | caclub_    |   | taxtmi_   |   | turbotax_    |
    | agent.py   |   | agent.py  |   | agent.py     |
    +------+------+   +------+------+   +------+--------+
           |                 |                 |
           +-----------------+-----------------+
                            |
                   Web Scraping (HTTP/Playwright/Stealth)
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
    +-------------+  +-------------+  +-------------+
    | CAClubIndia |  | TaxTMI.com |  | TurboTax   |
    | .com        |  |            |  | .intuit.com|
    +-------------+  +-------------+  +-------------+
```

### Component Roles

| Component | Role |
|-----------|------|
| **WebSocket Server (:8003)** | Handles real-time voice/audio communication using Google genai SDK, session management, and orchestrates live queries |
| **Root Agent (:8000)** | Orchestrator. Detects smalltalk, loads memory, dispatches to sub-agents, runs legal enrichment, finalizes response, persists memory |
| **Sub-Agents (CAClub, TaxTMI, TurboTax, TaxProfBlog)** | Each wraps a scraper behind an A2A server. Receives a query, runs the scraper, returns structured evidence |
| **Scrapers** | Standalone Python scripts that fetch and parse web pages from tax knowledge sites |
| **Legal Enrichment** | Fetches Indian Kanoon statutes and Casemine court judgements |
| **Memory System** | SQL (Cloud SQL/SQLite) + Vertex Memory Bank for user profiles, queries, concepts, entities, resolutions |
| **Graph API (:8006)** | FastAPI app exposing knowledge graph endpoints |

---

## Project Structure

```
TaxClarity/
├── config.py                     # Centralized configuration (env vars)
├── requirements.txt              # Python dependencies
├── pyproject.toml                # Project metadata (uv-compatible)
├── Dockerfile                    # Container build
├── Procfile                      # Process definitions for honcho
├── nginx.conf                    # Nginx configuration
├── run.sh                        # Start all backend servers
├── stop.sh                       # Stop all servers
│
├── agents/                       # ADK agents + scrapers
│   ├── agent.py                  # ADK web entrypoint
│   ├── caclub_agent.py           # CAClubIndia scraper
│   ├── taxtmi_agent.py           # TaxTMI scraper
│   ├── turbotax_agent.py         # TurboTax scraper
│   ├── taxprofblog_agent.py      # TaxProfBlog scraper
│   ├── calculation_agent.py      # Tax liability calculator
│   ├── contradiction_agent.py     # Contradiction detection
│   │
│   └── adk/                      # Google ADK A2A agents
│       ├── root_agent/           # Root orchestrator (:8000)
│       ├── caclub_a2a/           # CAClubIndia (:8001)
│       ├── taxtmi_a2a/           # TaxTMI (:8002)
│       ├── taxprofblog_a2a/      # TaxProfBlog (:8004)
│       ├── turbotax_a2a/         # TurboTax (:8005)
│       ├── geo_router/           # Geographic routing agent
│       └── cache.py              # File-based caching (SHA256 + TTL)
│
├── backend/                      # Backend services
│   ├── websocket_server.py       # WebSocket server (:8003) with Gemini Live SDK
│   ├── graph_api.py              # Knowledge graph API (:8006)
│   ├── live_orchestrator.py      # Live query orchestration
│   ├── session_state.py          # Session state management
│   ├── memory_bank.py            # Memory bank interface
│   ├── obsidian_graph.py         # Graph persistence
│   ├── bot.py                    # Bot utilities
│   ├── errors.py                 # Error definitions
│   ├── health.py                 # Health check endpoints
│   └── document_extractor.py     # Document extraction
│
├── memory/                       # Memory system
│   ├── memory_service.py         # Memory service abstraction
│   ├── sql_memory_store.py       # SQL (Cloud SQL) persistence
│   ├── spanner_graph.py          # Spanner property graph (optional)
│   ├── vertex_memory_bank.py     # Vertex AI memory bank adapter
│   ├── pageindex_store.py        # PageIndex integration
│   └── extractor.py              # Gemini-based extraction
│
├── frontend/                     # Next.js frontend (main)
│   ├── src/
│   │   ├── app/                 # Next.js app router
│   │   ├── components/          # React components
│   │   ├── hooks/               # Custom hooks
│   │   └── lib/                 # Utilities
│   └── package.json
│
├── frontend-next/                # Alternative Next.js frontend
│
├── schemas/                      # JSON schemas
│   └── a2a_schema.json
│
├── scripts/                      # Utility scripts
│   ├── spanner_init.py          # Initialize Spanner database
│   ├── verify_gcp.py            # Verify GCP setup
│   └── gcp_setup.sh             # GCP provisioning
│
├── tests/                        # Test suite
│   ├── agents/                  # Agent tests
│   ├── backend/                 # Backend tests
│   ├── memory/                  # Memory tests
│   ├── e2e/                     # End-to-end tests
│   └── manual/                  # Manual tests
│
├── demo/                         # Demo conversation logs
│
└── New_vertex/                   # Alternative vertex implementation
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend)
- Google Cloud project (optional for memory features)
- A Gemini API key

### Installation

**Using uv (recommended):**

```bash
# Clone and navigate to project
cd TaxClarity

# Install Python dependencies with uv
uv sync

# Install frontend dependencies
cd frontend
npm install
```

**Using pip:**

```bash
cd TaxClarity
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm install
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and fill in required variables:
#   GOOGLE_API_KEY=your_gemini_key
```

### Running

**Start all backend servers:**

```bash
./run.sh
```

This launches 7 services:
- `:8000` — Root orchestrator agent
- `:8001` — CAClubIndia sub-agent
- `:8002` — TaxTMI sub-agent
- `:8003` — WebSocket server
- `:8004` — TaxProfBlog sub-agent
- `:8005` — TurboTax sub-agent
- `:8006` — Graph API

**Start frontend:**

```bash
cd frontend
npm run dev
```

Then open http://localhost:3000 in your browser.

**Start with Docker:**

```bash
docker build -t taxclarity .
docker run -p 8000:8000 -p 3000:3000 taxclarity
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key |
| `SPANNER_PROJECT_ID` | No | — | Google Cloud project ID |
| `SPANNER_INSTANCE_ID` | No | — | Spanner instance ID |
| `SPANNER_DATABASE_ID` | No | — | Spanner database ID |
| `ROOT_AGENT_URL` | No | http://localhost:8000 | Root agent URL |
| `GRAPH_API_URL` | No | http://localhost:8006 | Graph API URL |
| `VOICE_MODEL` | No | gemini-2.5-flash-native-audio-preview-12-2025 | Gemini Live model |
| `TTS_MODEL` | No | gemini-2.5-flash-preview-tts | TTS model |
| `MEMORY_PROVIDER` | No | vertex_sql | Memory provider |
| `USE_VERTEX_MEMORY` | No | false | Use Vertex memory |
| `USE_CLOUD_SQL_MEMORY` | No | true | Use Cloud SQL memory |
| `DISABLE_SPANNER_MEMORY` | No | true | Disable Spanner memory |
| `CLOUD_SQL_DATABASE_URL` | No | sqlite:///taxagent_memory.db | Database URL |
| `SESSION_CACHE_TTL_MINUTES` | No | 15 | Session cache TTL |
| `MEMORY_BANK_ENABLED` | No | false | Enable memory bank |
| `MEMORY_BANK_ENDPOINT` | No | http://localhost:8080 | Memory bank endpoint |
| `LOG_LEVEL` | No | INFO | Logging level |

---

## Services

### A2A Agents

All agents communicate via the A2A (Agent-to-Agent) protocol:

| Port | Agent | Description |
|------|-------|-------------|
| 8000 | Root Agent | Main orchestrator |
| 8001 | CAClubIndia | Indian tax forum scraper |
| 8002 | TaxTMI | Indian tax forum scraper |
| 8004 | TaxProfBlog | US tax blog scraper |
| 8005 | TurboTax | US tax service scraper |

### Graph API

Exposes endpoints for knowledge graph operations:

- `GET /users` — List users
- `GET /sessions` — List sessions
- `GET /graph` — Get user knowledge graph
- `GET /health` — Health check

---

## Memory System

The memory system uses a layered approach:

### SQL Memory Store
- Primary persistence layer using Cloud SQL (PostgreSQL) or SQLite
- Stores sessions, queries, and conversation history

### Vertex Memory Bank (Optional)
- Integration with Google Vertex AI Memory Bank
- Enabled via `USE_VERTEX_MEMORY=true`

### Spanner (Disabled by Default)
- Property graph storage (optional)
- Enabled via `DISABLE_SPANNER_MEMORY=false`

### Memory Flow
```
User Query → Memory Service → SQL Store + Vertex Memory Bank
                                    ↓
                          Context Retrieval
                                    ↓
                          Response Enhancement
```

---

## Scraping Pipeline

All scrapers use a 3-tier fallback strategy:

1. **HTTP** — Fast, uses scrapling.Fetcher
2. **Dynamic** — Medium, uses Playwright headless browser
3. **Stealth** — Slow, uses anti-bot browser with Cloudflare solving

### Sources

| Source | Site | Content |
|--------|------|---------|
| CAClubIndia | caclubindia.com | Expert threads, forums |
| TaxTMI | taxtmi.com | Forums, articles |
| TurboTax | turbotax.intuit.com | Help articles |
| TaxProfBlog | taxprofblog.com | Blog articles |
| Indian Kanoon | indiankanoon.org | Statutes |
| Casemine | casemine.com | Court judgements |

---

## Deployment

### Google Cloud Run

```bash
gcloud run deploy taxclarity \
  --source . \
  --region us-central1 \
  --memory 2Gi --cpu 2 \
  --min-instances 1 \
  --set-env-vars "GOOGLE_API_KEY=..."
```

### Local with Honcho

```bash
honcho start -f Procfile
```

---

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, uvicorn
- **Agents:** Google ADK, A2A Protocol
- **LLM:** Google Gemini (google-genai SDK)
- **Memory:** SQLAlchemy (SQLite/PostgreSQL), Vertex Memory Bank
- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS
- **Package Management:** uv (Python), npm (JavaScript)
