# TaxClarity

TaxClarity is a Gemini Live powered, multi agent tax advisor for India, the US, and cross border scenarios. It connects live voice and vision, evidence gathering, and long term memory so users can speak naturally and receive cited guidance with a knowledge graph that evolves over time.

This README is aligned to the current codebase under `Taxclarity/` and the system diagram in `Architecture.png`.

## What This System Does

1. Accepts live user voice and optional camera input through the WebSocket chat interface.
2. Routes tax questions to the Root Agent which orchestrates specialist agents via A2A.
3. Collects evidence from CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog.
4. Builds responses with citations and contextualizes with long term memory.
5. Updates the live knowledge graph and optional document intelligence pipeline.

## Architecture Overview

The diagram in `Architecture.png` describes the flow:

1. Gemini Live handles voice and real time response streaming.
2. The WebSocket server coordinates the session, memory loading, and A2A tool calls.
3. The Root Agent dispatches to region specific agents in India and the US.
4. Vertex AI Memory Bank stores long term memory and feeds context back into prompts.
5. The Knowledge Graph is rendered from Obsidian format nodes updated in real time.
6. Optional document extraction uses Google Document AI with a Gemini Vision fallback.

## Related Repository for Document Vision

The document vision pipeline lives in a separate repository. You can find it here:

```
https://github.com/LE-TAPU-KOKO/Saul
```

## Key Principles

1. Gemini Live only for audio in and audio out.
2. Memory uses Vertex AI Memory Bank for long term context.
3. Evidence and citations must be visible and traceable in the UI.
4. The UI streams agent output and live transcriptions from Gemini Live.
5. The knowledge graph updates as the conversation evolves.

## Project Structure

All active runtime code lives under `Taxclarity/`.

1. `Taxclarity/backend` contains the WebSocket server, graph API, session state, memory bridge, and orchestration.
2. `Taxclarity/agents` contains the Root Agent and A2A sub agents for evidence sources.
3. `Taxclarity/memory` contains the Vertex memory bank adapter and extractors.
4. `Taxclarity/frontend` contains the Next.js UI used in production.
5. `Taxclarity/docs` contains deployment notes and operations guides.

## Installation

Recommended package manager is `uv`.

1. Install uv.
2. Create and activate a virtual environment.
3. Install dependencies.

Example:

```bash
cd Taxclarity
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

For frontend:

```bash
cd Taxclarity/frontend
npm install
```

## Environment Setup

Create a `.env` in `Taxclarity/`.

Required values:

1. `GOOGLE_API_KEY` for Gemini Live and Vertex AI Memory Bank
2. `ROOT_AGENT_URL` default `http://localhost:8000`
3. `GRAPH_API_URL` default `http://localhost:8006`
4. `VOICE_MODEL` for Gemini Live audio model

Important memory settings:

1. `MEMORY_PROVIDER` set to `vertex`
2. `USE_VERTEX_MEMORY` set to `true`
3. `USE_CLOUD_SQL_MEMORY` set to `false`

## Running Locally

Start backend services:

```bash
cd Taxclarity
./run.sh
```

This starts the following services:

1. Root Agent on `8000`
2. CAClubIndia agent on `8001`
3. TaxTMI agent on `8002`
4. WebSocket server on `8003`
5. TaxProfBlog agent on `8004`
6. TurboTax agent on `8005`
7. Graph API on `8006`

Start the frontend:

```bash
cd Taxclarity/frontend
npm run dev
```

Open `http://localhost:3000`.

## Knowledge Graph

1. The UI shows a live knowledge graph on the left panel.
2. Nodes and relationships are updated on each turn.
3. Data is stored in Obsidian format under `Taxclarity/data/obsidian_vault`.
4. The Graph API serves these nodes to the frontend.

## Memory System

Long term memory is handled by Vertex AI Memory Bank.

1. The memory service loads prior summaries and topics on session start.
2. The Root Agent injects that memory into the system prompt.
3. The graph is enriched from both user and agent turns.

## Evidence and Citations

1. Each agent returns structured evidence items.
2. The Root Agent synthesizes a single response with citations.
3. The UI renders sources and links in the right panel.

## Deployment

This repository supports Vercel for frontend and a Google Cloud VM for backend.

1. Vercel builds from `Taxclarity/frontend`.
2. Backend runs on a VM with systemd and Nginx.
3. WebSocket endpoint is exposed over TLS using Nginx.

See `Taxclarity/docs/deployment-vercel-gce.md` for operational steps.

Automated backend deployment is configured in:

```
.github/workflows/deploy-backend-vm.yml
```

## License

Internal project for the Gemini Live Agent Challenge.
