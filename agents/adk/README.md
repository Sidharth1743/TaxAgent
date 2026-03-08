# ADK + A2A Setup

This project uses **Google ADK** and **A2A** to let CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog agents negotiate a final answer using Gemini.

## Requirements
Install dependencies:

```bash
pip install -r requirements.txt
```

Set Gemini API key (from `.env`):

```bash
cp .env.example .env
# then edit .env and set GOOGLE_API_KEY
```

## Run A2A Agents

Run each agent in its own terminal (A2A servers via Uvicorn):

```bash
uvicorn agents.adk.caclub_a2a.agent:a2a_app --port 8001
```

```bash
uvicorn agents.adk.taxtmi_a2a.agent:a2a_app --port 8002
```

```bash
uvicorn agents.adk.turbotax_a2a.agent:a2a_app --port 8003
```

```bash
uvicorn agents.adk.taxprofblog_a2a.agent:a2a_app --port 8004
```

```bash
uvicorn agents.adk.root_agent.agent:a2a_app --port 8000
```

## Send a Query (Root Agent)
You can use any HTTP client to post to the root agent. Example:

```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{"input": "tax on hackathon winning"}'
```

### Source routing
You can force a single source by adding a directive to your query:

- `source:caclub tax on hackathon winning`
- `source:taxtmi tax on hackathon winning`
- `source:turbotax tax on hackathon winning`
- `source:taxprofblog tax on freelancer`
- `source:us tax on freelancer`
- `source:both tax on hackathon winning`

The root agent will ask both remote agents and respond with a cited answer.
