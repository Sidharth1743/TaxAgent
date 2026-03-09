 Here's a summary of the plan I've written:

  The core insight: Your backend is strong (top 5% of submissions for technical depth), but you're scoring near zero on the 40% multimodal UX criteria and missing required
   submission deliverables. The plan transforms this into a winning entry in 8 days.

  Key strategic decisions:
  1. Gemini Live ↔ ADK bridge pattern — Don't rewire agents for run_live(). Instead, a FastAPI WebSocket server connects to Gemini Live API and uses function calling to
  bridge into your existing A2A agents. Your whole backend stays untouched.
  2. Three-panel frontend — Knowledge graph (left) | Voice orb + chat (center) | Source evidence cards (right). Plain HTML + Tailwind, no React build chain.
  3. Document vision via Gemini multimodal — camera/upload → extract tax form data → feed into live session.
  4. Single Cloud Run container with supervisor running all 6 services.
  5. Cut Reddit agent, Vertex AI Memory Bank, 8-source expansion — not worth the hours, judges won't miss them.

  The demo script is designed to hit all three criteria in 4 minutes: voice Q&A with live source cards appearing (Innovation), architecture diagram + Cloud Run proof
  (Technical), and a cross-border NRI scenario with document scanning (wow factor).

  Day-by-day: Live server (Day 1) → Frontend + voice (Day 2) → Full integration (Day 3) → Vision + polish (Day 4) → Cloud deploy (Day 5) → Diagram + README (Day 6) →
  Record video (Day 7) → Submit (Day 8).

───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Ready to code?

 Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 TaxClarity — Gemini Live Agent Challenge: Winning Strategy

 Context

 We're competing in the Gemini Live Agent Challenge ($80K total, $25K grand prize, 7,572 participants, deadline March 16, 2026). The backend multi-agent system is strong
 (5 ADK agents, 6 scraper sources, Spanner graph memory, legal enrichment), but the project has zero frontend, zero Gemini Live integration, zero cloud deployment, zero
 demo/presentation materials. The evaluation heavily weights multimodal UX (40%), meaning we need a dramatic transformation from "backend prototype" to "polished
 voice-first product" in 8 days.

 Evaluation Criteria Breakdown

 - Innovation & Multimodal UX (40%) — "See, Hear, Speak" seamlessly. Distinct persona. Live, context-aware, not turn-based.
 - Technical Implementation (30%) — ADK/GenAI SDK usage. Google Cloud backend. Grounding. Error handling. No hallucinations.
 - Demo & Presentation (30%) — Problem/solution clarity. Architecture diagram. Cloud deployment proof. Working software in video.

 Submission Requirements

 1. Text description
 2. Public code repo with spin-up README
 3. Google Cloud deployment proof (screen recording)
 4. Architecture diagram
 5. Demo video (under 4 minutes)

 ---
 What's Built vs What's Missing

 Already Built (Strong Backend)

 - Google ADK + A2A multi-agent: 5 agents on ports 8000-8004
 - 4 scraper sub-agents (CAClubIndia, TaxTMI, TurboTax, TaxProfBlog)
 - 2 legal enrichment scrapers (Indian Kanoon, Casemine)
 - Spanner property graph memory (9 node tables, 10 edge types)
 - Gemini-based structured memory extraction with retry/validation
 - Response orchestration with citation enforcement + file-based caching
 - Graph visualization API (FastAPI + Cytoscape.js)

 Critical Gaps

 ┌────────────────────────────┬──────────────────────────────┬────────┐
 │            Gap             │       Impact on Score        │ Effort │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No Gemini Live voice/audio │ Kills 40% criteria           │ ~16h   │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No modern frontend         │ Kills UX + Demo              │ ~16h   │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No Cloud deployment        │ Fails submission requirement │ ~6h    │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No architecture diagram    │ Fails submission requirement │ ~3h    │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No demo video              │ Loses 30% criteria           │ ~8h    │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No document vision         │ Misses multimodal bonus      │ ~8h    │
 ├────────────────────────────┼──────────────────────────────┼────────┤
 │ No geo-routing             │ Minor gap                    │ ~4h    │
 └────────────────────────────┴──────────────────────────────┴────────┘

 ---
 Architecture Design

 Core Pattern: Gemini Live ↔ ADK Bridge

 DO NOT try to wire Runner.run_live() into the existing agents — too fragile. Instead, use a proxy bridge:

 Browser                          Cloud Run Container
 ┌──────────┐    WebSocket     ┌──────────────────────────────────┐
 │ Voice Orb├──── audio ──────►│ live/server.py (FastAPI)         │
 │ Chat     │◄── audio ───────│   ↕ Gemini Live API (WS)         │
 │ Graph    │    + text/json   │   ↕ Function Calls → bridge      │
 │ Sources  │                  │       ↓                           │
 │ DocScan  │                  │   ADK Root Agent :8000            │
 └──────────┘                  │     ├─ CAClub A2A :8001           │
                               │     ├─ TaxTMI A2A :8002           │
                               │     ├─ TurboTax A2A :8003         │
                               │     └─ TaxProfBlog A2A :8004      │
                               │                                    │
                               │   Spanner Graph ←→ memory_tools   │
                               │   Gemini Vision ←→ live/vision.py │
                               └──────────────────────────────────┘

 When Gemini Live triggers a function call (e.g. search_tax_knowledge), the server intercepts it, calls the existing ADK root agent via HTTP, feeds the structured JSON
 result back to Gemini Live, which generates a spoken response grounded in real data.

 Key Technical Decisions

 1. Gemini Live model: gemini-2.5-flash-native-audio-preview (required for audio I/O)
 2. Root agent model: Upgrade to gemini-2.5-flash (better reasoning)
 3. Sub-agents: Keep gemini-2.0-flash-lite (they just pass through JSON, no reasoning needed)
 4. Audio format: Input 16-bit PCM 16kHz mono → Output 24kHz
 5. Frontend: Plain HTML/JS/CSS with Tailwind CDN (no React build toolchain — save time)
 6. Deployment: Single Cloud Run container running all services via supervisor

 ---
 New Files to Create

 live/
   __init__.py
   server.py              # FastAPI app: WebSocket for Gemini Live, static file serving
   tools.py               # Function declarations for Live session (search, legal, vision, memory)
   audio_utils.py         # PCM encode/decode helpers
   vision.py              # Document image → Gemini multimodal → structured extraction

 frontend/
   index.html             # Three-panel SPA (graph | voice+chat | sources)
   app.js                 # WebSocket audio client, UI state management
   styles.css             # Tailwind + custom styles for voice orb, panels
   components/
     voice-orb.js         # Animated orb: idle (pulse), listening (expand), thinking (spin), speaking (wave)
     chat-panel.js        # Scrolling chat with citation chips
     graph-panel.js       # Embedded Cytoscape.js (reuse from static/graph.html)
     doc-scanner.js       # Camera capture + file upload
     source-cards.js      # Evidence cards with source logos

 Dockerfile               # Multi-stage: python:3.11-slim + playwright + all services
 docker-compose.yml       # Local dev compose
 cloudbuild.yaml          # Cloud Build for Cloud Run
 supervisor.conf          # Process manager for all 6 services in one container

 docs/
   architecture.png       # Professional architecture diagram (draw.io/Excalidraw)

 Files to Modify

 - agents/adk/root_agent/agent.py — Upgrade model to gemini-2.5-flash
 - memory/extractor.py — Upgrade model to gemini-2.5-flash
 - pyproject.toml — Add google-genai dependency for Live API
 - .env.example — Add Live API model config
 - README.md — Complete rewrite for hackathon submission

 ---
 Frontend Design (Three-Panel SPA)

 ┌─────────────────────────────────────────────────────────┐
 │  🏛️  TaxClarity — Your AI Tax Advisor    [🌙/☀️ ]  [?]
 ├──────────┬────────────────────────┬─────────────────────┤
 │          │                        │                     │
 │ KNOWLEDGE│   ╭──────────────╮     │  SOURCE EVIDENCE    │
 │  GRAPH   │   │  ◉ Voice Orb │     │                     │
 │          │   │  (animated)  │     │  ┌───────────────┐  │
 │ [Cyto.js │   ╰──────────────╯     │  │ 📄 CAClubIndia│  │
 │  graph   │                        │  │ Title...      │  │
 │  grows   │   ┌──────────────────┐ │  │ snippet...    │  │
 │  as you  │   │ Chat transcript  │ │  │ 🔗 url        │  │
 │  talk]   │   │ with citations   │ │  └───────────────┘  │
 │          │   │                  │ │                     │
 │          │   │ User: "Is hack.."│ │  ┌───────────────┐  │
 │          │   │ Agent: "Under..."│ │  │ ⚖️  Indian Kanoon│ │
 │          │   │   [Sec 56] [url] │ │  │ Section 56(2) │  │
 │          │   │                  │ │  │ content...    │  │
 │          │   └──────────────────┘ │  └───────────────┘  │
 │          │   ┌──────────────────┐ │                     │
 │          │   │ 💬 Type here...  │📷│                     │
 │          │   └──────────────────┘ │                     │
 ├──────────┴────────────────────────┴─────────────────────┤
 │  India 🇮🇳  |  USA 🇺🇸  |  Cross-border 🌍  | Memory
 └─────────────────────────────────────────────────────────┘

 Voice Orb States

 - Idle: Gentle blue pulse, breathing animation
 - Listening: Expanding teal rings synced to mic input volume
 - Thinking: Spinning gradient ring (agent is fetching from sources)
 - Speaking: Waveform ripples synced to output audio amplitude
 - Error: Red pulse with retry prompt

 Source Evidence Cards

 When agent cites a source, cards slide in from the right:
 - Source logo (CAClubIndia, Indian Kanoon, TurboTax, etc.)
 - Title, snippet, date, reply_count
 - Clickable URL
 - Confidence indicator (single vs multi-source corroboration)

 Knowledge Graph Panel

 - Reuse the Cytoscape.js code from static/graph.html
 - After each persist_memory_tool call, re-fetch graph data and animate new nodes appearing
 - Color-code by type: User (blue), Query (teal), Concept (orange), Entity (green), Resolution (purple)
 - Nodes pulse briefly when the agent references them

 ---
 Gemini Live Server Implementation (live/server.py)

 Endpoints

 - GET / — Serve frontend/index.html
 - WS /ws/live — Bidirectional audio streaming + function call bridge
 - POST /api/vision — Document image analysis
 - GET /api/graph, /api/users, /api/sessions — Proxy to existing graph_api.py
 - GET /health — Health check

 WebSocket Flow

 1. Client connects to /ws/live
 2. Server creates Gemini Live session:
      client.aio.live.connect(
        model="gemini-2.5-flash-native-audio-preview",
        config={
          response_modalities=["AUDIO", "TEXT"],
          system_instruction=TAXCLARITY_PERSONA,
          tools=TAX_TOOLS,  # from live/tools.py
        }
      )
 3. Two async tasks run concurrently:
    a. browser_to_gemini: receive audio bytes from WS → session.send_realtime_input()
    b. gemini_to_browser: session.receive() →
       - audio data → forward to WS as binary
       - text data → forward to WS as JSON {"type":"text","content":"..."}
       - tool_call → execute_tool() → session.send_tool_response()
       - interruption → send {"type":"interrupt"} to WS

 Function Call Bridge (live/tools.py)

 TAX_TOOLS = [
     {
         "name": "search_tax_knowledge",
         "description": "Search tax knowledge bases for evidence. Returns cited sources.",
         "parameters": {
             "type": "object",
             "properties": {
                 "query": {"type": "string", "description": "The tax question"},
                 "region": {"type": "string", "enum": ["india", "us", "all"],
                            "description": "india=CAClubIndia+TaxTMI, us=TurboTax+TaxProfBlog, all=everything"}
             },
             "required": ["query"]
         }
     },
     {
         "name": "get_legal_context",
         "description": "Fetch Indian Kanoon law sections and Casemine court judgements.",
         "parameters": {...}
     },
     {
         "name": "get_user_memory",
         "description": "Retrieve user's tax profile and prior resolutions from memory graph.",
         "parameters": {...}
     },
     {
         "name": "save_to_memory",
         "description": "Persist this conversation to the user's tax memory graph.",
         "parameters": {...}
     },
     {
         "name": "analyze_document",
         "description": "Analyze a tax document (Form 16, W-2, ITR, etc.) from camera/upload.",
         "parameters": {...}
     }
 ]

 When search_tax_knowledge is called with region="india", the bridge sends the query with source:both directive to http://localhost:8000 (the existing root A2A agent) and
  returns the evidence JSON.

 System Persona (Gemini Live system instruction)

 You are TaxClarity, a warm and knowledgeable AI tax advisor. Your voice is professional
 but approachable — think trusted family accountant. You cover both Indian and US tax law,
 with special expertise in NRI cross-border situations.

 RULES:
 - ALWAYS use search_tax_knowledge before answering tax questions. NEVER answer from memory alone.
 - Cite specific URLs when making claims. Say "According to a CAClubIndia expert thread..."
 - If a question spans India AND US tax, search both regions.
 - Detect jurisdiction from context: Section 80C → India, 401k → US, DTAA → cross-border.
 - If unsure of jurisdiction, ASK the user.
 - Use get_user_memory at the start of conversations to personalize advice.
 - After answering a substantive question, call save_to_memory to build the user's profile.
 - When the user shows a document, call analyze_document and explain what you see.
 - Be concise in speech — long pauses lose the user. Aim for 2-3 sentences per response turn.

 ---
 Cloud Deployment Strategy

 Dockerfile

 FROM python:3.11-slim
 RUN apt-get update && apt-get install -y --no-install-recommends \
     supervisor wget gnupg && rm -rf /var/lib/apt/lists/*
 # Install Playwright browsers for scraping fallback
 RUN pip install playwright && playwright install chromium --with-deps
 COPY requirements.txt .
 RUN pip install --no-cache-dir -r requirements.txt
 COPY . /app
 WORKDIR /app
 COPY supervisor.conf /etc/supervisor/conf.d/taxclarity.conf
 EXPOSE 8080
 CMD ["supervisord", "-n"]

 supervisor.conf

 Runs all 6 processes (5 A2A agents + live server on port 8080) in a single container.

 Cloud Run Config

 - Region: us-central1 (near Spanner instance)
 - Memory: 2Gi, CPU: 2
 - Min instances: 1 (avoid cold starts for demo)
 - Timeout: 300s
 - Env vars: GOOGLE_API_KEY, SPANNER_* vars
 - Service account with Spanner Database User role

 ---
 Demo Video Script (4 minutes)

 [0:00–0:25] Hook + Problem Statement

 Screen shows: statistics overlay animation
 "Tax advice costs $200 per hour. 1.5 billion people across India and the US file taxes annually, many with cross-border complexity. NRIs face conflicting regulations
 between two countries. Meet TaxClarity — an AI tax advisor that can see your documents, hear your questions, and speak expert-backed answers in real time."

 [0:25–1:15] Live Voice Conversation (India)

 Screen shows: TaxClarity frontend on Cloud Run URL
 Open the app. Click the voice orb. It starts pulsing.
 - User: "Hi, I'm Sridevi. I work at TCS and want to know about tax saving options."
 - Agent: (warm voice) "Hello Sridevi! Let me check the latest expert advice on tax saving..." (orb shows thinking state, source cards slide in from right)
 - Agent: "According to CAClubIndia experts, you can claim deductions under Section 80C up to 1.5 lakhs — this includes EPF, PPF, ELSS, and life insurance. TaxTMI also
 confirms that NPS contributions under Section 80CCD(1B) give you an additional 50,000 deduction..."
 - Knowledge graph shows new nodes appearing: "Section 80C", "NPS", "Sridevi" user node

 [1:15–1:50] Document Vision

 - User: "Let me show you my Form 16." (clicks camera icon, holds up Form 16)
 - Agent: "I can see your Form 16 from TCS for FY 2024-25. Your gross salary is 12.4 lakhs, TDS deducted is 1.8 lakhs. I notice you haven't claimed full 80C deductions —
 you still have room for about 45,000 more. Would you like me to suggest the best options?"
 - Chat shows extracted form data, graph adds "TCS" entity, "FY 2024-25" node

 [1:50–2:25] Cross-Border NRI Query

 - User: "Actually, I'm moving to the US next month on an H-1B. How does this affect my taxes?"
 - Agent: "Great question! This is a cross-border situation. Let me search both Indian and US sources..." (shows both India and US source cards)
 - Agent: "Under the India-US DTAA, you can claim foreign tax credit to avoid double taxation. According to Indian Kanoon Section 90, and IRS Publication 54..." (legal
 enrichment cards appear)
 - Graph now shows connections between India and US jurisdiction nodes

 [2:25–3:05] Architecture + Technical Deep Dive

 Switch to architecture diagram
 "TaxClarity is built on Google ADK with 5 agents communicating via A2A protocol. The root agent orchestrates 4 specialized scraper agents covering CAClubIndia, TaxTMI,
 TurboTax, and TaxProfBlog. Legal enrichment fetches live Indian Kanoon statutes and Casemine court judgements. Every claim is grounded in real sources — no
 hallucination.

 User context is stored in a Spanner property graph with 9 node types and 10 relationship types, building a persistent tax profile across sessions. The Gemini Live API
 enables natural voice conversation with real-time function calling into the agent network.

 Everything runs on Cloud Run with a single container managing all services."

 [3:05–3:35] Cloud Deployment Proof

 Screen recording of GCP Console
 Show: Cloud Run service list → TaxClarity service → Revisions tab → Metrics.
 Show: Spanner instance → Database → Tables.
 Show: Cloud Run URL in browser bar → working app.

 [3:35–3:55] Memory Graph Visualization

 Back to app, click graph panel
 Show the full knowledge graph built during the conversation. Highlight: "Every conversation enriches the user's tax profile. Next time Sridevi comes back, TaxClarity
 remembers her employer, salary, deductions, and NRI status."

 [3:55–4:00] Closing

 "TaxClarity. See, Hear, Speak — tax advice without borders. Built with Gemini Live, Google ADK, Spanner Graph, and Cloud Run."

 ---
 Day-by-Day Schedule

 Day 1 (Mar 8): Gemini Live Server + Audio Bridge

 - Create live/server.py — FastAPI + WebSocket + Gemini Live session
 - Create live/tools.py — Function declarations
 - Create live/audio_utils.py — PCM helpers
 - Test: Python WebSocket client sends audio → gets spoken response back
 - Test: Function call bridge → calls existing root agent → returns data

 Day 2 (Mar 9): Frontend Shell + Voice Interaction

 - Create frontend/index.html — Three-panel layout with Tailwind
 - Create frontend/app.js — WebSocket audio client (AudioWorklet for 16kHz capture, AudioContext for 24kHz playback)
 - Create voice orb animation (CSS keyframes + JS audio level visualization)
 - Wire up: speak → orb listens → agent responds → orb speaks
 - Test: Full voice loop working in browser

 Day 3 (Mar 10): End-to-End Integration + Source Cards

 - Connect function call results to source evidence panel (cards with logos, snippets, URLs)
 - Connect graph panel to Spanner (reuse Cytoscape.js from static/graph.html)
 - Real-time graph updates after memory persist
 - Chat transcript with citation chips
 - Text input fallback
 - Test: Ask a tax question by voice → see sources + graph update live

 Day 4 (Mar 11): Document Vision + Geo-routing + Polish

 - Create live/vision.py — Camera/upload → Gemini multimodal extraction
 - Add camera button + file upload in frontend
 - Add auto geo-routing in system prompt (detect India/US/cross-border from query terms)
 - UI polish: loading states, connection indicator, error handling, mobile responsive
 - Upgrade model strings: root agent + extractor → gemini-2.5-flash

 Day 5 (Mar 12): Cloud Deployment

 - Write Dockerfile (python:3.11-slim + playwright + supervisor)
 - Write supervisor.conf for all 6 processes
 - Local docker build + test
 - Deploy to Cloud Run (gcloud run deploy)
 - Verify: Spanner connectivity, full voice flow on public URL
 - Record GCP Console screen for deployment proof

 Day 6 (Mar 13): Architecture Diagram + README

 - Create professional architecture diagram (draw.io/Excalidraw with Google Cloud icons)
 - Write comprehensive README for hackathon submission
 - Pre-warm caches: run all demo queries so scraper results are cached
 - Populate demo user in Spanner graph for rich memory display
 - Dry-run the demo script

 Day 7 (Mar 14): Demo Video

 - Script final demo (see script above)
 - Record with OBS or screen recorder + microphone
 - Edit: add title cards, architecture diagram overlay, statistics
 - Record GCP Console proof segment separately
 - Export under 4 minutes, upload to YouTube

 Day 8 (Mar 15): Submit

 - Final testing on deployed URL
 - Fix any demo-breaking bugs
 - Write submission text (problem, solution, tech stack, learnings)
 - Submit to DevPost before deadline

 ---
 What to CUT (save time, judges won't miss)

 - ❌ Reddit agent — not worth the hours, existing 4 sources are sufficient
 - ❌ Vertex AI Memory Bank — Spanner graph is already impressive
 - ❌ All 8 planned US sources — 2 is enough (TurboTax + TaxProfBlog)
 - ❌ Separate geo-router agent — system prompt detection is sufficient
 - ❌ React/Vue/build toolchain — plain HTML+Tailwind is faster and sufficient

 What to EMPHASIZE in Demo (judges will remember)

 - ✅ Voice orb animation — visceral, shows "live" not "turn-based"
 - ✅ Source cards appearing in real-time — shows grounding visually
 - ✅ Knowledge graph growing — unique, memorable
 - ✅ Document scanning — "see" in "See, Hear, Speak"
 - ✅ Cross-border query — demonstrates real-world complexity
 - ✅ URL citations that judges can actually click

 Pre-Demo Preparation (Critical)

 1. Pre-warm scraper caches for exact demo queries (run them the day before)
 2. Pre-populate Spanner with a demo user "Sridevi" with some prior history
 3. Set Cloud Run min-instances=1 to avoid cold start during recording
 4. Test demo script 5+ times before recording
 5. Have text fallback visible in case audio glitches during recording

 ---
 Verification

 After implementation:
 1. docker build -t taxclarity . succeeds
 2. docker run -p 8080:8080 taxclarity starts all 6 services
 3. Open http://localhost:8080 — three-panel UI loads
 4. Click voice orb → microphone permission granted → audio streams
 5. Ask "What is Section 80C?" → agent speaks answer with citations
 6. Source cards appear in right panel with clickable URLs
 7. Knowledge graph in left panel adds new nodes
 8. Click camera → capture/upload Form 16 → agent reads it
 9. gcloud run deploy succeeds → public URL works
 10. GCP Console shows Cloud Run service + Spanner instance
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
