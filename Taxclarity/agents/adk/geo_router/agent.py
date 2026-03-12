#!/usr/bin/env python3
"""
Geo Router Agent using ADK with true A2A delegation.
Routes tax queries to appropriate jurisdiction-based agent clusters via Agent Cards.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import structlog

from config import (
    CACLUB_AGENT_URL,
    GEO_ROUTER_MODEL,
    GOOGLE_API_KEY,
    TAXPROFBLOG_AGENT_URL,
    TAXTMI_AGENT_URL,
    TURBOTAX_AGENT_URL,
)

logger = structlog.get_logger(__name__)

AGENT_ENDPOINTS = {
    "india": [
        CACLUB_AGENT_URL,   # CAClubIndia
        TAXTMI_AGENT_URL,   # TaxTMI
    ],
    "usa": [
        TAXPROFBLOG_AGENT_URL,  # TaxProfBlog
        TURBOTAX_AGENT_URL,     # TurboTax
    ],
}


@dataclass
class AgentCard:
    name: str
    description: str
    jurisdiction: str
    capabilities: List[str]
    endpoint: str
    language: str


async def fetch_agent_card(endpoint: str) -> Optional[AgentCard]:
    """Fetch agent card from a specific endpoint URL"""
    url = f"{endpoint}/.well-known/agent.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return AgentCard(
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    jurisdiction=data.get("jurisdiction", ""),
                    capabilities=data.get("capabilities", []),
                    endpoint=data.get("endpoint", endpoint),
                    language=data.get("language", "en"),
                )
    except Exception as e:
        logger.warning("failed_to_fetch_agent_card", endpoint=endpoint, error=str(e))
    return None


async def fetch_agent_cards_for_jurisdiction(jurisdiction: str) -> List[AgentCard]:
    """Fetch agent cards for ALL endpoints in a jurisdiction's list"""
    endpoints = AGENT_ENDPOINTS.get(jurisdiction, [])
    cards = []
    for endpoint in endpoints:
        card = await fetch_agent_card(endpoint)
        if card:
            cards.append(card)
    return cards


async def fetch_all_agent_cards() -> Dict[str, List[AgentCard]]:
    """Fetch agent cards for all jurisdictions, keyed by jurisdiction"""
    cards = {}
    for jurisdiction in AGENT_ENDPOINTS.keys():
        jurisdiction_cards = await fetch_agent_cards_for_jurisdiction(jurisdiction)
        if jurisdiction_cards:
            cards[jurisdiction] = jurisdiction_cards
    return cards


async def determine_jurisdiction_with_llm(query: str) -> Dict[str, Any]:
    """Use LLM to determine jurisdiction based on query"""
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)

    prompt = f"""Analyze this tax query and determine the jurisdiction:

Query: {query}

Return a JSON with:
- "jurisdiction": "india", "usa", or "both"
- "reasoning": brief explanation
- "confidence": 0.0-1.0

Consider:
- India: Form 16, Section 44ADA, TDS, GST, ₹, INR, Indian tax years
- USA: W-2, 1099, IRS, federal tax, $, US tax years
- Both: cross-border income, international freelancers"""

    try:
        response = await client.aio.models.generate_content(
            model=GEO_ROUTER_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "system_instruction": "You are a tax jurisdiction classifier. Return only valid JSON.",
            }
        )

        result = json.loads(response.text)
        return {
            "jurisdiction": result.get("jurisdiction", "both"),
            "reasoning": result.get("reasoning", ""),
            "confidence": result.get("confidence", 0.5),
        }
    except Exception as e:
        logger.error("llm_classification_failed", error=str(e))
        # Fallback to keyword matching -- normalize keys to match LLM response format
        fallback = await keyword_based_routing(query)
        return {
            "jurisdiction": fallback.get("jurisdiction", "both"),
            "reasoning": fallback.get("method", "keyword"),
            "confidence": 0.8,
        }


async def delegate_to_agent(agent_endpoint: str, query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """Delegate query to a worker agent via A2A protocol"""
    task_id = str(uuid.uuid4())

    a2a_message = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": "tasks/send",
        "params": {
            "task": {
                "id": task_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": query}]
                }
            }
        }
    }

    if context:
        a2a_message["params"]["task"]["context"] = context

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{agent_endpoint}/",
                json=a2a_message,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                return {
                    "status": "success",
                    "task_id": task_id,
                    "response": response.json()
                }
            else:
                return {
                    "status": "error",
                    "task_id": task_id,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
    except Exception as e:
        return {
            "status": "error",
            "task_id": task_id,
            "error": str(e)
        }


async def route_and_delegate(query: str, user_context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Main entry point: Determine jurisdiction and delegate to appropriate agent(s).
    Returns synthesized result from all delegated agents.
    """
    import asyncio

    # Step 1: Determine jurisdiction using LLM
    routing = await determine_jurisdiction_with_llm(query)
    jurisdiction = routing.get("jurisdiction", "both")

    # Step 2: Fetch agent cards for discovery
    agent_cards = await fetch_all_agent_cards()

    # Step 3: Collect endpoints to delegate to
    target_jurisdictions = ["india", "usa"] if jurisdiction == "both" else [jurisdiction]

    tasks = []
    task_labels = []  # track (jurisdiction, endpoint) for each task
    for j in target_jurisdictions:
        endpoints = AGENT_ENDPOINTS.get(j, [])
        for endpoint in endpoints:
            tasks.append(delegate_to_agent(endpoint, query, user_context))
            task_labels.append((j, endpoint))

    if not tasks:
        return {
            "status": "error",
            "message": f"No agent available for jurisdiction: {jurisdiction}"
        }

    # Step 4: Delegate in parallel to ALL endpoints
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    results = {}
    for (j, endpoint), result in zip(task_labels, results_list):
        key = f"{j}:{endpoint}"
        if isinstance(result, Exception):
            results[key] = {"status": "error", "error": str(result)}
        else:
            results[key] = result

    # Step 5: Synthesize final response
    # Build flat card info for response
    card_info = {}
    for j, cards_list in agent_cards.items():
        for card in cards_list:
            card_info[f"{j}:{card.endpoint}"] = {
                "name": card.name,
                "jurisdiction": card.jurisdiction,
                "capabilities": card.capabilities,
            }

    return {
        "status": "success",
        "query": query,
        "routing": routing,
        "agent_cards": card_info,
        "delegation_results": results,
        "synthesized_response": synthesize_response(results, jurisdiction),
    }


def synthesize_response(results: Dict[str, Any], jurisdiction: str) -> str:
    """Synthesize final response from delegation results.

    Keys in *results* are formatted as ``jurisdiction:endpoint``.
    """
    jurisdiction_responses: Dict[str, str] = {}

    for key, result in results.items():
        if result.get("status") == "success":
            task_result = result.get("response", {})
            if "result" in task_result:
                jurisdiction_responses[key] = task_result["result"]

    if not jurisdiction_responses:
        return "I couldn't get a response from the tax agents. Please try again."

    if jurisdiction == "both":
        return "\n\n".join([
            f"**{key.split(':')[0].upper()} ({key.split(':', 1)[1]}):**\n{resp}"
            for key, resp in jurisdiction_responses.items()
        ])
    else:
        # Return all matching responses concatenated
        return "\n\n".join(jurisdiction_responses.values())


async def keyword_based_routing(query: str) -> Dict[str, Any]:
    """Simple keyword-based jurisdiction detection fallback.
    Used when the LLM-based route_and_delegate fails."""
    q = query.lower()
    india_keywords = [
        "india", "gst", "tds", "section 80c", "section 80d", "pan",
        "aadhaar", "itr", "income tax india", "epf", "nps",
        "huf", "hra", "lta", "80ccd", "44ada", "old regime",
        "new regime", "rupee", "inr", "lakhs", "crore",
    ]
    usa_keywords = [
        "usa", "us", "irs", "1040", "w-2", "w2", "401k", "401(k)",
        "roth", "social security", "medicare", "standard deduction",
        "itemized", "schedule c", "earned income", "eitc",
        "dollar", "usd", "federal tax", "state tax",
    ]
    india_score = sum(1 for kw in india_keywords if kw in q)
    usa_score = sum(1 for kw in usa_keywords if kw in q)

    if india_score > 0 and usa_score > 0:
        return {"jurisdiction": "both", "type": "cross_border", "method": "keyword"}
    elif india_score > usa_score:
        return {"jurisdiction": "india", "type": "single", "method": "keyword"}
    elif usa_score > india_score:
        return {"jurisdiction": "usa", "type": "single", "method": "keyword"}
    else:
        return {"jurisdiction": "both", "type": "default", "method": "keyword"}


# Simple function for ADK tool compatibility
async def route_to_jurisdiction(query: str) -> Dict[str, Any]:
    """ADK tool wrapper for routing"""
    return await determine_jurisdiction_with_llm(query)


def create_geo_router_agent():
    """Create the Geo Router LlmAgent with A2A delegation"""
    try:
        from google.adk.agents.llm_agent import Agent

        return Agent(
            name="geo_router",
            model=GEO_ROUTER_MODEL,
            description="Routes tax queries to India or USA tax agent clusters via A2A protocol",
            instruction=(
                "You are the Geo Router. Your job is to:\n"
                "1. Analyze the user's query to determine their tax jurisdiction using LLM.\n"
                "2. Dynamically fetch agent cards from /.well-known/agent.json for each jurisdiction.\n"
                "3. Delegate the query to the appropriate tax agent(s) via A2A HTTP requests.\n"
                "4. If the query spans both jurisdictions, delegate to all agents in parallel.\n"
                "5. Synthesize the final answer from all delegated responses.\n"
                "\n"
                "Available endpoints:\n"
                f"- India Tax Agents: {CACLUB_AGENT_URL} (CAClubIndia), {TAXTMI_AGENT_URL} (TaxTMI)\n"
                f"- USA Tax Agents: {TAXPROFBLOG_AGENT_URL} (TaxProfBlog), {TURBOTAX_AGENT_URL} (TurboTax)\n"
            ),
            tools=[route_to_jurisdiction, fetch_all_agent_cards, delegate_to_agent],
        )
    except ImportError as e:
        logger.error("adk_not_available", error=str(e))
        return None


geo_router_agent = create_geo_router_agent()

