# TaxAgent — Multi-Agent Tax Advisory System

TaxAgent is an AI-powered tax advisory system that aggregates evidence from multiple Indian and US tax knowledge sources, enriches answers with legal citations from court judgements and statutes, and maintains a persistent memory graph of each user's tax profile. It is built on **Google ADK** (Agent Development Kit) with the **A2A** (Agent-to-Agent) protocol, backed by **Google Cloud Spanner** as a property graph database and **Gemini** as the LLM backbone.

---

## Table of Contents

1. [How It Works — User Perspective](#how-it-works--user-perspective)
2. [Technical Architecture](#technical-architecture)
3. [Data Flow](#data-flow)
4. [Directory Structure](#directory-structure)
5. [Getting Started](#getting-started)
6. [CLI Reference](#cli-reference)
7. [Environment Variables](#environment-variables)
8. [Graph Database Schema](#graph-database-schema)
9. [Scraping Pipeline](#scraping-pipeline)
10. [Caching Strategy](#caching-strategy)

---

## How It Works — User Perspective

1. **You ask a tax question** — e.g., *"Is hackathon prize money taxable under Section 56?"*
2. **TaxAgent checks if it's smalltalk** — greetings get a friendly reply with a capabilities overview.
3. **Memory context is loaded** — if you've asked questions before, past resolutions and your tax profile (jurisdiction, entities, prior ambiguities) are pulled from the Spanner graph.
4. **Evidence is gathered in parallel** — the root agent dispatches your query to 2-4 sub-agents depending on a source directive:
   - `source:both` (default) — CAClubIndia + TaxTMI (Indian tax forums)
   - `source:us` — TurboTax + TaxProfBlog (US tax sources)
   - `source:all` — all four sources
   - `source:caclub`, `source:taxtmi`, `source:turbotax`, `source:taxprofblog` — single source
5. **Legal enrichment runs** — Indian Kanoon statutes and Casemine court judgements matching referenced sections are fetched in parallel via subprocess scrapers.
6. **The answer is finalized** — evidence is merged, claims are formed with inline URL citations, confidence is raised when multiple sources agree, and the response JSON is structured.
7. **Memory is persisted** — the query, extracted concepts, entities, jurisdictions, tax forms, and resolution status are written to the Spanner property graph for future context.

### Source Directive Syntax

Append a directive anywhere in your query to control which sources are used:

```
What is Section 80C deduction limit? source:both
How do I report freelance income? source:us
Is gift from mother-in-law taxable? source:all
```

---

## Technical Architecture

```
                         +---------------------+
                         |     User / Client    |
                         +----------+----------+
                                    |
                                    | A2A Protocol (HTTP JSON)
                                    v
                         +----------+----------+
                         |    Root Agent :8000   |
                         |  (taxclarity_root)   |
                         +----+----+----+------+
                              |    |    |    |
              +---------------+    |    |    +----------------+
              |                    |    |                     |
              v                    v    v                     v
     +--------+------+   +--------+--+ +--+--------+  +------+--------+
     | CAClub  :8001 |   | TaxTMI    | |  TurboTax |  | TaxProfBlog   |
     | A2A Agent     |   | :8002     | |  :8003    |  | :8004         |
     +--------+------+   +--------+--+ +--+--------+  +------+--------+
              |                    |         |                 |
              v                    v         v                 v
     +--------+------+   +--------+--+ +----+------+  +------+--------+
     | caclub_agent  |   | taxtmi    | | turbotax  |  | taxprofblog   |
     | .py (scraper) |   | _agent.py | | _agent.py |  | _agent.py     |
     +---------------+   +-----------+ +-----------+  +---------------+
              \                 |             |               /
               \                |             |              /
                +-------+-------+-------------+-------------+
                        |  Web (Scrapling: HTTP/Playwright/Stealth)
                        v
              +---------+---------+
              | CAClubIndia.com   |
              | TaxTMI.com        |
              | TurboTax.intuit   |
              | TaxProfBlog.com   |
              +-------------------+

     Parallel Legal Enrichment (subprocess):

     +-------------------+     +-------------------+
     | taxkanoon_        |     | casemine_         |
     | sections.py       |     | judgements.py     |
     | (Indian Kanoon)   |     | (Casemine.com)    |
     +-------------------+     +-------------------+

     Memory Layer:

     +-------------------+     +-------------------+
     | Gemini Extractor  | --> | Spanner Property  |
     | (extractor.py)    |     | Graph (9 tables)  |
     +-------------------+     +-------------------+

     Graph Visualization:

     +-------------------+
     | graph_api.py      |
     | FastAPI :9000     |
     | + static/graph.html
     +-------------------+
```

### Component Roles

| Component | Role |
|---|---|
| **Root Agent** | Orchestrator. Detects smalltalk, loads memory, dispatches to sub-agents, runs legal enrichment, finalizes response, persists memory. |
| **Sub-Agents (4)** | Each wraps a scraper behind an A2A server. Receives a query, runs the scraper, returns structured `{query, source, evidence[]}` JSON. |
| **Scrapers (4)** | Standalone Python scripts that fetch and parse web pages from tax knowledge sites. Use a 3-tier fallback: HTTP -> Playwright -> Stealth browser. |
| **Legal Enrichment** | Two subprocess scrapers (Indian Kanoon for statutes, Casemine for judgements) run in parallel via `ThreadPoolExecutor`. |
| **Memory Extractor** | Calls Gemini to extract structured data (concepts, entities, jurisdictions, forms, intent) from query+answer text. |
| **Spanner Graph** | Persistent property graph storing Users, Sessions, Queries, Concepts, TaxEntities, Jurisdictions, TaxForms, Resolutions, Ambiguities, and typed Edges. |
| **Graph API** | FastAPI app exposing `/users`, `/sessions`, `/graph` endpoints + a Cytoscape.js web UI for visualizing the knowledge graph. |

---

## Data Flow

### Request Lifecycle (non-smalltalk tax query)

```
1. User sends query
       |
2. is_smalltalk_tool(query)  -->  {is_smalltalk: false}
       |
3. get_memory_context_tool(query, user_id)
       |-- Gemini extracts concepts/entities from query
       |-- Spanner: SELECT prior resolutions matching concepts/entities
       |-- Returns {prior_resolutions, unresolved_queries}
       |
4. fetch_both_a2a(query)  [or fetch_us_a2a / fetch_all_a2a]
       |-- HTTP POST to sub-agent A2A servers (parallel)
       |-- Each sub-agent runs scraper subprocess
       |-- Each sub-agent returns {source, evidence[{title, url, snippet, date, reply_count}]}
       |-- Root receives merged evidence dict
       |
5. Root LLM drafts answer JSON with claims + citations
       |
6. run_legal_enrichment_tool(query, draft_json)
       |-- Extracts section references (e.g., "Section 80C")
       |-- Runs taxkanoon_sections.py + casemine_judgements.py in parallel
       |-- Returns {sections, judgements, errors}
       |
7. finalize_response(query, evidence, draft_json, legal_context)
       |-- Enforces source attribution
       |-- Validates citation URLs against evidence
       |-- Formats claims with bullets
       |-- Returns final JSON payload
       |
8. persist_memory_tool(query, user_id, session_id, answer_json)
       |-- Gemini extracts structured memory from query+answer
       |-- Writes to Spanner: Query, Resolution, Concepts, Entities, Edges
       |
9. Final JSON returned to user
```

### Evidence JSON Schema (per sub-agent)

```json
{
  "query": "is hackathon prize taxable",
  "source": "caclub",
  "evidence": [
    {
      "title": "Tax on Hackathon Prize — Expert Thread",
      "url": "https://www.caclubindia.com/experts/...",
      "snippet": "Under Section 56(2)(ib), any sum received...",
      "date": "15 March 2025",
      "reply_count": 3
    }
  ]
}
```

### Final Response JSON Schema

```json
{
  "query": "is hackathon prize taxable",
  "sources": ["CAClubIndia", "TaxTMI"],
  "claims": [
    {
      "claim": "Hackathon prizes above Rs 50,000 are taxable under Section 56(2)(ib) as income from other sources.",
      "citations": ["https://www.caclubindia.com/experts/..."]
    }
  ],
  "bullets": [
    "- Hackathon prizes above Rs 50,000 are taxable... (https://...)"
  ],
  "legal_context": {
    "sections": [...],
    "judgements": [...]
  }
}
```

---

## Directory Structure

```
TaxAgent/
|-- main.py                        # CLI entry point (serve / graph-api / scrape)
|-- start_adk_servers.sh           # Bash script to launch all 5 A2A servers
|-- graph_api.py                   # FastAPI graph visualization API (:9000)
|-- logging_config.py              # Structured JSON logging setup
|-- taxkanoon_sections.py          # Indian Kanoon statute scraper
|-- casemine_judgements.py         # Casemine judgement scraper
|-- .env.example                   # Template for environment variables
|
|-- scraping/
|   |-- __init__.py
|   |-- utils.py                   # Shared: fetch_with_fallbacks, is_blocked, page_html, etc.
|
|-- memory/
|   |-- __init__.py
|   |-- spanner_graph.py           # Spanner schema, read/write, graph queries
|   |-- extractor.py               # Gemini structured extraction (retry + validation)
|
|-- agents/
|   |-- caclub_agent.py            # CAClubIndia scraper (expert threads, forums, articles)
|   |-- taxtmi_agent.py            # TaxTMI scraper (forums, articles, news)
|   |-- turbotax_agent.py          # TurboTax scraper (Cludo API + HTML)
|   |-- taxprofblog_agent.py       # TaxProfBlog scraper
|   |
|   |-- adk/
|       |-- __init__.py
|       |-- cache.py               # Shared file-based caching (SHA256 + TTL)
|       |
|       |-- root_agent/            # Root orchestrator (decomposed)
|       |   |-- agent.py           # Agent definition + tool registration
|       |   |-- a2a_client.py      # A2A HTTP client + fetch factories
|       |   |-- query_utils.py     # Source directives, section extraction, text utils
|       |   |-- legal_enrichment.py# Indian Kanoon + Casemine subprocess runner
|       |   |-- memory_tools.py    # Spanner memory fetch/persist
|       |   |-- smalltalk.py       # Smalltalk detection + response
|       |   |-- response.py        # Response finalization + citation enforcement
|       |
|       |-- caclub_a2a/            # CAClubIndia A2A server (:8001)
|       |-- taxtmi_a2a/            # TaxTMI A2A server (:8002)
|       |-- turbotax_a2a/          # TurboTax A2A server (:8003)
|       |-- taxprofblog_a2a/       # TaxProfBlog A2A server (:8004)
|
|-- static/
|   |-- graph.html                 # Cytoscape.js knowledge graph visualization
|
|-- data/                          # Cache files, scraper output (gitignored)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Google Cloud project with Spanner instance (optional — system works without it, memory features disabled)
- A Gemini API key

### Installation

```bash
git clone <repo-url> && cd TaxAgent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Playwright browsers (needed for dynamic/stealth scraping)
playwright install chromium
```

### Configuration

```bash
cp .env.example .env
# Edit .env and fill in at minimum:
#   GOOGLE_API_KEY=your_gemini_key
#   (Spanner vars if you want memory persistence)
```

### Running

**Start all agents (recommended):**
```bash
./start_adk_servers.sh
# or
python main.py serve
```

This launches 5 servers:
- `:8000` — Root orchestrator agent
- `:8001` — CAClubIndia sub-agent
- `:8002` — TaxTMI sub-agent
- `:8003` — TurboTax sub-agent
- `:8004` — TaxProfBlog sub-agent

**Start the graph visualization API:**
```bash
python main.py graph-api
# Serves on http://localhost:9000
# Web UI at http://localhost:9000/
# Health check at http://localhost:9000/health
```

**Run a scraper standalone:**
```bash
python main.py scrape caclub --query "tax on freelance income"
python main.py scrape casemine --query "section 80C"
python main.py scrape taxkanoon --query "section 56 Income Tax Act doctypes:laws"
```

### Interacting with the Root Agent

The root agent speaks the A2A protocol. You can interact with it using any A2A-compatible client, or programmatically:

```python
import asyncio, httpx, uuid
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import Message, Part, TextPart

async def ask(query: str):
    client = await ClientFactory.connect(
        "http://localhost:8000",
        client_config=ClientConfig(streaming=False, polling=True,
            httpx_client=httpx.AsyncClient(timeout=httpx.Timeout(180.0))),
    )
    msg = Message(
        messageId=str(uuid.uuid4()), role="user",
        parts=[Part(root=TextPart(text=query))],
    )
    async for result in client.send_message(msg):
        print(result)

asyncio.run(ask("Is hackathon prize money taxable in India?"))
```

---

## CLI Reference

```
python main.py <command>

Commands:
  serve       Start all 5 A2A agent servers (ports 8000-8004)
  graph-api   Start the Spanner graph visualization API (port 9000)
  scrape      Run a scraper directly

Scrape usage:
  python main.py scrape <scraper> --query "..." [--max-links N]

  Scrapers: caclub, taxtmi, turbotax, taxkanoon, casemine
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key for LLM calls and memory extraction |
| `SPANNER_PROJECT_ID` | No | — | Google Cloud project ID for Spanner |
| `SPANNER_INSTANCE_ID` | No | — | Spanner instance ID |
| `SPANNER_DATABASE_ID` | No | — | Spanner database ID |
| `CLUDO_CUSTOMER_ID` | No | — | TurboTax Cludo search API customer ID |
| `CLUDO_ENGINE_ID` | No | — | TurboTax Cludo search API engine ID |
| `CLUDO_SITE_KEY` | No | — | TurboTax Cludo API site key |
| `CLUDO_API_URL` | No | — | TurboTax Cludo API base URL |
| `CASEMINE_COOKIE` | No | — | Authenticated cookie for Casemine API |
| `SCRAPER_TIMEOUT_MS` | No | `30000` | Stealth browser timeout in milliseconds |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |
| `CACHE_TTL_SECONDS` | No | `600` | File-based cache TTL for sub-agent results |

---

## Scraping Pipeline

All scrapers use a shared 3-tier fallback strategy (defined in `scraping/utils.py`):

```
1. HTTP (fast, ~1s)
   Uses scrapling.Fetcher — plain HTTP GET with response parsing.
   If the page returns a block/captcha page, falls through.

2. Dynamic (medium, ~5s)
   Uses scrapling.DynamicFetcher — headless Playwright browser.
   Waits for JS rendering and network idle.
   If still blocked, falls through.

3. Stealth (slow, ~15-30s)
   Uses scrapling.StealthyFetcher — anti-bot browser with
   Cloudflare solving, fingerprint randomization.
   Timeout controlled by SCRAPER_TIMEOUT_MS env var.
```

### Block Detection

Pages are checked for block indicators: "captcha", "verify you are human", "access denied", "cloudflare", "just a moment", "attention required". Each scraper can add site-specific patterns.

### Per-Source Details

| Source | Site | Content Types | Special Notes |
|---|---|---|---|
| **CAClubIndia** | caclubindia.com | Expert threads, forums, articles | Google Custom Search for discovery |
| **TaxTMI** | taxtmi.com | Forums, articles, news | Similar structure to CAClub |
| **TurboTax** | turbotax.intuit.com | Articles, help pages | Cludo search API preferred over HTML |
| **TaxProfBlog** | taxprofblog.com | Blog articles | Standard article extraction |
| **Indian Kanoon** | indiankanoon.org | Statutes, case law | Akoma Ntoso XML parsing for sections |
| **Casemine** | casemine.com | Court judgements | JSON API + cookie auth, cited-in extraction |

---

## Caching Strategy

### Sub-Agent Level (caclub, taxtmi)

- **Mechanism:** File-based JSON cache in `data/` directory
- **Key:** SHA256 hash of query string (with optional prefix)
- **TTL:** 600 seconds (10 minutes) by default
- **Implementation:** `agents/adk/cache.py` — `cached_run()` function
- **Behavior:** If a cache file exists and is younger than TTL, the scraper is skipped entirely

### Graph API Level

- **Mechanism:** Module-level singleton for the Spanner database handle
- **Behavior:** Connection is created once on first request and reused for all subsequent requests

### Memory Extraction

- **Mechanism:** Gemini API call with 3-attempt retry and exponential backoff
- **Validation:** Response must be valid JSON with `concepts` and `intent` keys
- **Robustness:** Markdown code fences are stripped before JSON parsing
