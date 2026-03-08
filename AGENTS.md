# Repository Guidelines

## Project Structure & Module Organization
- `agents/`: Core agent implementations and A2A wrappers (see `agents/adk/` for A2A server apps).
- `main.py`: Small scraping/demo script that fetches a TaxTMI article.
- `start_adk_servers.sh`: Convenience script to run the three A2A servers.
- `taxkanoon_sections.py`: Indian Kanoon search + section scraper (writes per‑section `.txt`).
- `casemine_judgements.py`: Casemine judgements scraper via JSON API (writes per‑judgement `.txt`).
- `schemas/`: JSON schema files used by the agents.
- `data/`: Local data assets used by agents (if present).
- `dumps/`, `dumps_taxtmi/`, `*_results.json`, `*_search.json`: Collected or cached outputs.
- `.adk/` and `agents/.adk/`: Local runtime artifacts (treat as generated).

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: Create/activate a virtual environment.
- `pip install -r requirements.txt`: Install runtime dependencies.
- `python main.py`: Run the demo scraper in `main.py`.
- `./start_adk_servers.sh`: Launch A2A servers on ports `8000`–`8004`.
- `python taxkanoon_sections.py --query "section 80c doctypes:laws"`: Fetch Indian Kanoon search results + section text files.
- `python casemine_judgements.py --query "income from other source"`: Fetch Casemine judgements + text files (reads cookies from `casemine_cookies.txt` or `CASEMINE_COOKIE`).

If you need environment variables (e.g., `GOOGLE_API_KEY`), add them to a local `.env` file; the startup script loads it automatically.
Casemine API requires cookies; store them in `casemine_cookies.txt` or set `CASEMINE_COOKIE` in `.env`.

## Coding Style & Naming Conventions
- Python style: follow PEP 8 with 4-space indentation.
- Naming: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- No formatter/linter is configured; keep changes small and consistent with nearby code.

## Testing Guidelines
- No test framework or `tests/` directory is currently present.
- If you add tests, prefer `pytest` and place them under `tests/` with names like `test_<module>.py`.

## Commit & Pull Request Guidelines
- Git history is empty, so there is no established commit-message convention yet.
- Suggested convention for new commits: `feat: ...`, `fix: ...`, `chore: ...` (Conventional Commits style).
- Pull requests should include:
  - A short summary of changes and motivation.
  - Any relevant commands run (e.g., `python main.py`).
  - Notes about new dependencies or environment variables.

## Security & Configuration Tips
- Do not commit secrets. Keep API keys in `.env` and add new secrets to your local environment only.
- Treat files under `.adk/` as generated unless you explicitly need to version them.
