# TaxAgent Share Package

This folder is a clean handoff copy of the currently working TaxAgent stack for local development and manual git push.

It includes:
- `frontend-next` for the active Next.js UI
- `backend` for the websocket server, graph API, document extraction, and live orchestration
- `agents` for the A2A source agents and root agent
- `memory` for Spanner/PageIndex persistence helpers
- `schemas`, `data`, `scripts`, `tests`, and `docs`
- launch scripts: `run.ps1`, `start_servers.ps1`, `start_adk_servers.sh`

It does not include generated/local-only artifacts such as:
- `.venv`
- `frontend-next/node_modules`
- `frontend-next/.next`
- local `.env`
- logs and cache folders

## Prerequisites

- Windows PowerShell
- Python 3.11+ recommended
- Node.js 20+ and npm
- Google API access for Gemini
- Optional:
  - Google Document AI for W-2 / 1099 extraction
  - Google Cloud Spanner for graph persistence
  - PageIndex for document retrieval support

## Setup

From this folder:

```powershell
cd X:\path\to\taxagent-share-package-v1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then install frontend dependencies:

```powershell
cd X:\path\to\taxagent-share-package-v1\frontend-next
npm install
```

## Environment

Copy `.env.example` to `.env` in the package root and fill in the values you actually use:

```powershell
cd X:\path\to\taxagent-share-package-v1
Copy-Item .env.example .env
```

Important variables:
- `GOOGLE_API_KEY`
- `VOICE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025`
- `SOURCE_AGENT_MODEL=gemini-3.1-flash-lite-preview`
- `ROOT_AGENT_MODEL=gemini-3.1-flash-lite-preview`
- `GEO_ROUTER_MODEL=gemini-3.1-flash-lite-preview`
- `EXTRACTOR_MODEL=gemini-3.1-flash-lite-preview`
- `SPANNER_PROJECT_ID`
- `SPANNER_INSTANCE_ID`
- `SPANNER_DATABASE_ID`
- `DOCAI_LOCATION`
- `DOCAI_PROCESSOR_ID`
- `PAGEINDEX_API_KEY`

Notes:
- W-2 / 1099 extraction will use Document AI only if `DOCAI_PROCESSOR_ID` is set.
- Form 16 currently falls back to Gemini extraction, not Document AI.
- If Spanner is not configured, the app still runs, but graph persistence is limited.

## Run

Fastest local start:

```powershell
cd X:\path\to\taxagent-share-package-v1
.\.venv\Scripts\Activate.ps1
.\run.ps1
```

That starts:
- root agent on `:8000`
- CAClub India on `:8001`
- TaxTMI on `:8002`
- websocket server on `:8003`
- TaxProfBlog on `:8004`
- TurboTax on `:8005`
- graph API on `:8006`
- frontend on `http://localhost:3000`

Manual backend-only start:

```powershell
cd X:\path\to\taxagent-share-package-v1
.\.venv\Scripts\Activate.ps1
.\start_servers.ps1
```

Then in another terminal:

```powershell
cd X:\path\to\taxagent-share-package-v1\frontend-next
npm run dev
```

## Useful checks

Frontend:

```powershell
cd X:\path\to\taxagent-share-package-v1\frontend-next
npm run lint
npm run build
```

Backend tests:

```powershell
cd X:\path\to\taxagent-share-package-v1
.\.venv\Scripts\Activate.ps1
pytest -q tests\backend
```

## Current behavior notes

- The live voice flow uses Gemini Live with reconnect hardening and conversation memory filtering.
- W-2 compute now normalizes raw Box labels into canonical compute fields before tax calculation.
- The transparency graph is enabled and shows live/memory events.
- Duplicate timeline key warnings were fixed in this package.

## What your friend should push

Push the contents of this folder as a separate git root or copy this folder into a new repo and run:

```powershell
git init
git add .
git commit -m "feat: share taxagent working package"
```

Then add their remote and push normally.
