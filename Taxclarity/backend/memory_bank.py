#!/usr/bin/env python3
"""
Memory Bank integration for proactive tax advice.
Queries user state and provides personalized greetings.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
import structlog

from config import MEMORY_BANK_ENABLED, MEMORY_BANK_ENDPOINT, MEMORY_SPANNER_DIRECT

logger = structlog.get_logger(__name__)

# Spanner-direct fallback for memory fetch
try:
    from memory.spanner_graph import get_client, load_config as load_spanner_config
    SPANNER_DIRECT_AVAILABLE = True
except ImportError:
    SPANNER_DIRECT_AVAILABLE = False


@dataclass
class UserTaxState:
    """User's tax-related state from Memory Bank"""
    user_id: str
    jurisdiction: str
    income_range: Optional[str]
    tax_regime: Optional[str]  # old vs new for India
    deductions_claimed: List[str]
    upcoming_deadlines: List[Dict[str, str]]
    last_interaction: Optional[str]
    proactive_reminders: List[str]
    prior_topics: List[str] = None

    def __post_init__(self):
        if self.prior_topics is None:
            self.prior_topics = []


async def fetch_user_tax_state(user_id: str) -> Optional[UserTaxState]:
    """Fetch user tax state from Memory Bank, with Spanner-direct fallback."""
    result = None

    if MEMORY_BANK_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{MEMORY_BANK_ENDPOINT}/users/{user_id}/tax-state"
                )

                if response.status_code == 200:
                    data = response.json()
                    result = UserTaxState(
                        user_id=data.get("user_id", user_id),
                        jurisdiction=data.get("jurisdiction", "unknown"),
                        income_range=data.get("income_range"),
                        tax_regime=data.get("tax_regime"),
                        deductions_claimed=data.get("deductions_claimed", []),
                        upcoming_deadlines=data.get("upcoming_deadlines", []),
                        last_interaction=data.get("last_interaction"),
                        proactive_reminders=data.get("proactive_reminders", []),
                    )
        except Exception as e:
            logger.warning("memory_bank_fetch_failed", error=str(e))

    # Spanner-direct fallback
    if result is None and MEMORY_SPANNER_DIRECT and SPANNER_DIRECT_AVAILABLE:
        result = await _fetch_from_spanner(user_id)

    return result


async def _fetch_from_spanner(user_id: str) -> Optional[UserTaxState]:
    """Fetch user tax state directly from Spanner graph as fallback."""
    try:
        cfg = load_spanner_config()
        if cfg is None:
            return None

        db = get_client(cfg)

        query = """
        SELECT q.text, q.intent, c.name AS concept, e.name AS entity, e.jurisdiction
        FROM Queries q
        JOIN Edges eq ON eq.from_id = q.query_id AND eq.type = 'REFERENCES'
        JOIN Concepts c ON c.concept_id = eq.to_id
        LEFT JOIN Edges ee ON ee.from_id = q.query_id AND ee.type = 'INVOLVES'
        LEFT JOIN TaxEntities e ON e.entity_id = ee.to_id
        JOIN Sessions s ON s.session_id = q.session_id
        WHERE s.user_id = @user_id
        ORDER BY q.created_at DESC
        LIMIT 10
        """

        from google.cloud.spanner_v1 import param_types
        results = db.execute_sql(
            query,
            params={"user_id": user_id},
            param_types={"user_id": param_types.STRING},
        )

        rows = list(results)
        if not rows:
            return None

        # Extract jurisdiction, deductions, and prior topics from results
        jurisdictions = set()
        deductions = []
        prior_topics = []

        for row in rows:
            text, intent, concept, entity, jurisdiction = row

            if jurisdiction:
                jurisdictions.add(jurisdiction.lower())

            if concept:
                concept_lower = concept.lower()
                if "section" in concept_lower or "80" in concept_lower:
                    deduction_key = concept_lower.replace(" ", "_")
                    if deduction_key not in deductions:
                        deductions.append(deduction_key)

            topic = intent or text
            if topic and topic not in prior_topics:
                prior_topics.append(topic)

        # Determine primary jurisdiction
        if len(jurisdictions) == 1:
            jurisdiction_str = jurisdictions.pop()
        elif jurisdictions:
            jurisdiction_str = "cross-border"
        else:
            jurisdiction_str = "unknown"

        return UserTaxState(
            user_id=user_id,
            jurisdiction=jurisdiction_str,
            income_range=None,
            tax_regime=None,
            deductions_claimed=deductions,
            upcoming_deadlines=[],
            last_interaction=None,
            proactive_reminders=[],
            prior_topics=prior_topics[:5],
        )

    except Exception as e:
        logger.warning("spanner_direct_fetch_failed", error=str(e))
        return None


def generate_proactive_greeting(user_state: UserTaxState) -> str:
    """Generate personalized greeting based on user tax state"""
    guidance = []

    # Jurisdiction-specific greeting
    if user_state.jurisdiction == "india":
        guidance.append("Primary jurisdiction: India.")

        # Check tax regime
        if user_state.tax_regime == "new":
            guidance.append("User appears to prefer the new regime.")
        elif user_state.tax_regime == "old":
            guidance.append("User appears to have used the old regime with 80C deductions.")

        # Check for common deductions
        if "section_80c" not in user_state.deductions_claimed:
            guidance.append("Section 80C may still have room.")

        if "section_44ada" not in user_state.deductions_claimed:
            guidance.append("Section 44ADA may be relevant if freelance income exists.")

    elif user_state.jurisdiction == "usa":
        guidance.append("Primary jurisdiction: USA.")

        if user_state.income_range:
            guidance.append(f"Income range on record: {user_state.income_range}.")

    else:
        guidance.append("Cross-border tax context may apply.")

    # Add upcoming deadlines
    if user_state.upcoming_deadlines:
        deadlines = [d.get("name", d.get("description", "")) for d in user_state.upcoming_deadlines[:2]]
        if deadlines:
            guidance.append(f"Upcoming deadlines: {', '.join(deadlines)}")

    # Add proactive reminders
    if user_state.proactive_reminders:
        reminders = user_state.proactive_reminders[:2]
        for reminder in reminders:
            guidance.append(f"Reminder: {reminder}")

    return " ".join(guidance)


async def get_proactive_prompt(user_id: str) -> Optional[str]:
    """
    Get proactive system prompt for Gemini Live.
    Called when WebSocket connection is established (type == "start").
    """
    user_state = await fetch_user_tax_state(user_id)

    if not user_state:
        return None

    greeting = generate_proactive_greeting(user_state)

    # Build system prompt with user context
    system_prompt = f"""User tax profile and prior context:
{greeting}

Use this as background context. Do not open with a fresh welcome unless this is genuinely the first turn.
When the user speaks with you:
1. Reference their specific tax situation when relevant
2. Offer personalized suggestions based on their profile
3. Mention deadlines and important dates proactively
4. Suggest deductions they might be missing

User Profile:
- Jurisdiction: {user_state.jurisdiction}
- Tax Regime: {user_state.tax_regime or 'Not set'}
- Income Range: {user_state.income_range or 'Not set'}
- Claimed Deductions: {', '.join(user_state.deductions_claimed) or 'None'}

Be conversational and helpful, but continue the current thread instead of restarting it."""

    if user_state.prior_topics:
        system_prompt += f"\n\nPrevious topics discussed: {', '.join(user_state.prior_topics)}"

    return system_prompt


def should_push_initial_message(user_state: UserTaxState) -> bool:
    """Determine if we should push an initial proactive message"""
    # Push if there are reminders or upcoming deadlines
    if user_state.proactive_reminders:
        return True
    if user_state.upcoming_deadlines:
        return True
    return False


# Store for active sessions
_active_sessions: Dict[str, UserTaxState] = {}


async def register_session(user_id: str, session_id: str) -> Optional[UserTaxState]:
    """Register a new session and get user state"""
    user_state = await fetch_user_tax_state(user_id)
    if user_state:
        _active_sessions[session_id] = user_state
    return user_state


def get_session_state(session_id: str) -> Optional[UserTaxState]:
    """Get user state for active session"""
    return _active_sessions.get(session_id)


async def close_session(session_id: str):
    """Clean up session"""
    if session_id in _active_sessions:
        del _active_sessions[session_id]
