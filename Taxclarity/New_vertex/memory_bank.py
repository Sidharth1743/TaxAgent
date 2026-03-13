#!/usr/bin/env python3
"""User-memory helpers backed by MemoryService."""

from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog

from memory.memory_service import get_memory_service

logger = structlog.get_logger(__name__)


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
    try:
        context = await get_memory_service().load_conversation_context(user_id=user_id)
        prior_topics = [
            topic.get("topic", "")
            if isinstance(topic, dict)
            else str(topic)
            for topic in (context.get("top_topics", []) or context.get("prior_topics", []) or [])
        ]
        prior_topics = [topic for topic in prior_topics if topic]
        if not context.get("loaded") and not prior_topics:
            return None

        jurisdictions = set()
        deductions = []
        haystack = " ".join(
            prior_topics
            + [context.get("summary", "")]
            + [turn.get("text", "") for turn in context.get("recent_turns", [])]
        ).lower()

        if any(marker in haystack for marker in ("form 16", "80c", "80d", "gst", "india", "tds")):
            jurisdictions.add("india")
        if any(marker in haystack for marker in ("w-2", "1099", "irs", "federal tax", "usa", "us tax")):
            jurisdictions.add("usa")
        for marker in ("80c", "80d", "hsa", "401k", "eitc"):
            if marker in haystack and marker not in deductions:
                deductions.append(marker)

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
            prior_topics=prior_topics[:5] or [turn.get("text", "") for turn in context.get("recent_turns", [])[:3]],
        )
    except Exception as e:
        logger.warning("memory_bank_fetch_failed", error=str(e), user_id=user_id)
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
