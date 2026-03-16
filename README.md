# TaxClarity — Multi-Agent Tax Advisory System

TaxClarity is an AI-powered tax advisory system that aggregates evidence from multiple Indian and US tax knowledge sources, enriches answers with legal citations from court judgements and statutes, and maintains a persistent memory graph of each user's tax profile. It is built on **Google ADK** (Agent Development Kit) with the **A2A** (Agent-to-Agent) protocol, backed by **Google Cloud Spanner** as a property graph database and **Gemini** as the LLM backbone.

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

![Architecture](./Architecture.png)

### Component Roles

| Component | Role |
|-----------|------|
| **WebSocket Server (:8003)** | Handles real-time voice/audio communication, session management, and orchestrates live queries |
| **Root Agent (:8000)** | Orchestrator. Detects smalltalk, loads memory, dispatches to sub-agents, runs legal enrichment, finalizes response, persists memory |
| **Sub-Agents (CAClub, TaxTMI, TurboTax, TaxProfBlog)** | Each wraps a scraper behind an A2A server. Receives a query, runs the scraper, returns structured evidence |
| **Scrapers** | Standalone Python scripts that fetch and parse web pages from tax knowledge sites |
| **Legal Enrichment** | Fetches Indian Kanoon statutes and Casemine court judgements |
| **Memory System** | Spanner property graph + SQL persistence for user profiles, queries, concepts, entities, resolutions |
| **Graph API (:8006)** | FastAPI app exposing knowledge graph endpoints |

---

## Project Structure

```
TaxClarity/
├── config.py                     # Centralized configuration (env vars)
├── requirements.txt              # Python dependencies
├── pyproject.toml                # Project metadata
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
│   ├── calculation_agent.py       # Tax liability calculator
│   ├── contradiction_agent.py     # Contradiction detection
│   │
│   └── adk/                      # Google ADK A2A agents
│       ├── root_agent/           # Root orchestrator (:8000)
│       ├── caclub_a2a/           # CAClubIndia (:8001)
│       ├── taxtmi_a2a/           # TaxTMI (:8002)
│       ├── taxprofblog_a2a/       # TaxProfBlog (:8004)
│       ├── turbotax_a2a/         # TurboTax (:8005)
│       ├── geo_router/           # Geographic routing agent
│       └── cache.py              # File-based caching (SHA256 + TTL)
│
├── backend/                      # Backend services
│   ├── websocket_server.py         # WebSocket server (:8003)
│   ├── graph_api.py               # Knowledge graph API (:8006)
│   ├── live_orchestrator.py       # Live query orchestration
│   ├── session_state.py           # Session state management
│   ├── memory_bank.py             # Memory bank interface
│   ├── obsidian_graph.py          # Graph persistence
│   ├── bot.py                     # Bot utilities
│   ├── errors.py                  # Error definitions
│   ├── health.py                  # Health check endpoints
│   └── document_extractor.py      # Document extraction
│
├── memory/                        # Memory system
│   ├── memory_service.py          # Memory service abstraction
│   ├── sql_memory_store.py        # SQL (Cloud SQL) persistence
│   ├── spanner_graph.py            # Spanner property graph
│   ├── vertex_memory_bank.py       # Vertex AI memory bank adapter
│   ├── pageindex_store.py          # PageIndex integration
│   └── extractor.py                # Gemini-based extraction
│
├── frontend-next/                 # Next.js frontend (recommended)
│   ├── src/
│   │   ├── app/                   # Next.js app router
│   │   ├── components/            # React components
│   │   ├── hooks/                 # Custom hooks
│   │   └── lib/                   # Utilities
│   └── package.json
│
├── frontend/                      # Legacy vanilla JS frontend
│
├── schemas/                       # JSON schemas
│   └── a2a_schema.json
│
├── scripts/                       # Utility scripts
│   ├── spanner_init.py            # Initialize Spanner database
│   ├── verify_gcp.py              # Verify GCP setup
│   └── gcp_setup.sh               # GCP provisioning
│
├── tests/                         # Test suite
│   ├── agents/                    # Agent tests
│   ├── backend/                   # Backend tests
│   ├── memory/                    # Memory tests
│   ├── e2e/                       # End-to-end tests
│   └── manual/                    # Manual tests
│
├── demo/                          # Demo conversation logs
│
└── New_vertex/                    # Alternative vertex implementation
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend)
- Google Cloud project with Spanner instance (optional)
- A Gemini API key

### Installation

```bash
# Clone and navigate to project
cd TaxClarity

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies (if using frontend-next)
cd frontend-next
npm install
cd ..
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and fill in required variables:
#   GOOGLE_API_KEY=your_gemini_key
#   (Spanner vars if you want memory persistence)
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

**Start frontend (Next.js):**

```bash
cd frontend-next
npm run dev
```

Then open http://localhost:3000 in your browser.


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

### Spanner Property Graph

Models user tax knowledge as a connected graph:

**Node Tables:**
- Users, Sessions, Queries
- Concepts (e.g., "Section 80C", "Capital Gains")
- TaxEntities (salary, property, investments)
- Jurisdictions (India, US)
- TaxForms (ITR-1, W-2)
- Resolutions, Ambiguities

**Edge Types:**
- User --HAS_SESSION--> Session
- Session --CONTAINS--> Query
- Query --REFERENCES--> Concept
- Query --RESOLVED_BY--> Resolution
- TaxEntity --GOVERNED_BY--> Jurisdiction

### SQL Memory

Alternative memory using Cloud SQL (PostgreSQL/SQLite) for session persistence.

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

