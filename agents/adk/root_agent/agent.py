#!/usr/bin/env python3
"""
Root A2A agent orchestrating CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog agents via ADK.
Produces evidence-weighted answer with inline URL citations.
"""

import os

from google.adk.agents.llm_agent import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from dotenv import load_dotenv

from .a2a_client import (
    fetch_caclub_a2a,
    fetch_taxtmi_a2a,
    fetch_turbotax_a2a,
    fetch_taxprofblog_a2a,
    fetch_both_a2a,
    fetch_us_a2a,
    fetch_all_a2a,
)
from .legal_enrichment import run_legal_enrichment_tool
from .memory_tools import get_memory_context_tool, persist_memory_tool
from .smalltalk import is_smalltalk_tool, smalltalk_response_tool
from .response import finalize_response

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Load environment variables (e.g., GOOGLE_API_KEY) from .env
load_dotenv(os.path.join(ROOT, ".env"))


root_agent = Agent(
    name="taxclarity_root",
    model="gemini-3.1-flash-lite-preview",
    description="Reconciles CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog evidence into a single cited answer.",
    instruction=(
        "You are the root agent. For every user query:\n"
        "1) If the user specifies a source directive, follow it:\n"
        "   - 'source:caclub' => only CAClubIndia\n"
        "   - 'source:taxtmi' => only TaxTMI\n"
        "   - 'source:turbotax' => only TurboTax\n"
        "   - 'source:taxprofblog' => only TaxProfBlog\n"
        "   - 'source:us' => TurboTax + TaxProfBlog\n"
        "   - 'source:all' => CAClubIndia + TaxTMI + TurboTax + TaxProfBlog\n"
        "   - 'source:both' or no directive => CAClubIndia + TaxTMI\n"
        "2) If source is both, call fetch_both_a2a (parallel) to get evidence.\n"
        "   If source is us, call fetch_us_a2a (parallel) to get evidence.\n"
        "   If source is all, call fetch_all_a2a (parallel) to get evidence.\n"
        "   If source is single, call the matching single-source tool.\n"
        "3) Use ONLY the returned JSON evidence (title/url/snippet/date/reply_count).\n"
        "4) Merge evidence; if both sources support the same claim, raise confidence.\n"
        "5) Prefer replies (threads with responses) for higher confidence.\n"
        "6) Return ONLY valid JSON (no markdown, no prose).\n"
        "7) JSON schema:\n"
        "   {\n"
        "     \"query\": string,\n"
        "     \"sources\": [string],\n"
        "     \"message\": string (optional, for smalltalk),\n"
        "     \"bullets\": [string],\n"
        "     \"legal_context\": { ... } (optional),\n"
        "     \"claims\": [\n"
        "       {\n"
        "         \"claim\": string,\n"
        "         \"citations\": [string]\n"
        "       }\n"
        "     ]\n"
        "   }\n"
        "8) Citations MUST be URLs from evidence items. Do NOT use source names as citations.\n"
        "9) Always include a non-empty citations list per claim; if evidence is weak, still cite the closest relevant URL.\n"
        "10) The \"sources\" list MUST exactly match the data sources you called:\n"
        "    - source:us => [\"TurboTax\", \"TaxProfBlog\"]\n"
        "    - source:both => [\"CAClubIndia\", \"TaxTMI\"]\n"
        "    - source:all => [\"CAClubIndia\", \"TaxTMI\", \"TurboTax\", \"TaxProfBlog\"]\n"
        "    - single source => only that source.\n"
        "11) ALWAYS call is_smalltalk_tool first.\n"
        "    - If is_smalltalk=true, call smalltalk_response_tool and return ONLY its JSON.\n"
        "12) ALWAYS call get_memory_context_tool next and use it as context.\n"
        "13) After drafting your answer JSON, call run_legal_enrichment_tool to fetch law sections and judgements in parallel.\n"
        "14) Then call finalize_response with the legal_context and return ONLY its JSON.\n"
        "15) After returning, call persist_memory_tool to store memory (use session_id='session:'+uuid4()).\n"
    ),
    tools=[
        fetch_caclub_a2a,
        fetch_taxtmi_a2a,
        fetch_turbotax_a2a,
        fetch_taxprofblog_a2a,
        fetch_both_a2a,
        fetch_us_a2a,
        fetch_all_a2a,
        get_memory_context_tool,
        is_smalltalk_tool,
        smalltalk_response_tool,
        run_legal_enrichment_tool,
        persist_memory_tool,
        finalize_response,
    ],
)


a2a_app = to_a2a(root_agent, port=8000)
