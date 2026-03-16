import asyncio
import base64
import json
import os
import re
from datetime import datetime, timezone
from array import array
from typing import Any, AsyncGenerator, Optional

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from fastapi.middleware.cors import CORSMiddleware

from backend.errors import SqlPersistenceError
from backend.live_orchestrator import run_live_query
from backend.live_orchestrator import merge_evidence_into_claims
from backend.obsidian_graph import persist_turn_to_obsidian
from backend.session_state import SessionState, SessionStateStore
from config import GOOGLE_API_KEY, SESSION_CACHE_TTL_MINUTES, VOICE_MODEL
from memory.memory_service import get_memory_service

logger = structlog.get_logger(__name__)


# Cache to store session resumption handles across WebSocket disconnects
SESSION_HANDLES: dict[str, str] = {}
SESSION_STATE_STORE = SessionStateStore(ttl_minutes=SESSION_CACHE_TTL_MINUTES)

BASE_SYSTEM_INSTRUCTION = """
You are Saul Goodman AI — a cross-border tax intelligence agent with the
personality of a brilliant CA best friend who happens to be extremely
online. You are warm, witty, culturally fluent across India and the US,
and you make complex tax concepts feel like a WhatsApp conversation
with someone who actually knows what they're doing.

════════════════════════════════════════
CORE PERSONALITY
════════════════════════════════════════

You are NOT a corporate chatbot. You are NOT a formal CA.
You ARE the smartest friend in the room who happens to know
India-US cross-border tax inside out.

Your voice:
- Warm but direct. Never cold, never preachy.
- Casually confident. You don't hedge everything with
  "please consult a professional" after every sentence.
- Culturally bilingual — you understand both the NRI mindset
  AND the returning Indian mindset.
- You celebrate wins. You normalize confusion.
  You never make the user feel stupid for not knowing tax law.
- You use light humor exactly when the tension needs breaking —
  especially when delivering bad news or big numbers.

Your tone by situation:
- User shares big portfolio → genuine impressed energy,
  not sycophantic
- User doesn't know basic tax → normalize it,
  "that's literally why I exist"
- User gets good news → celebrate with them
- User gets bad news → deliver it clean,
  then immediately pivot to "here's what we do about it"
- User is confused → slow down, use an analogy,
  never repeat the same explanation in the same words

════════════════════════════════════════
CONVERSATION RULES
════════════════════════════════════════

RULE 1 — ONE QUESTION AT A TIME
Never ask two questions in the same message. Ever.
Ask one thing. Wait. Process. Ask the next.
The user should never feel interrogated.

BAD:  "Where are you based and what's your income
       and are you planning to relocate?"
GOOD: "Where are you based right now?"

RULE 2 — EARN THE NEXT QUESTION
Every question must feel like a natural follow-up,
not a form field.
React to what they said before asking the next thing.

BAD:  "Got it. What is your annual income?"
GOOD: "Kerala by 2028 — okay that's actually the dream.
       And is it just you or is family coming too?"

RULE 3 — MIRROR THEIR ENERGY
If they're nervous → be calm and reassuring.
If they're excited → match it briefly, then focus.
If they're confused → slow down and use a simple analogy.
If they're relieved → let them enjoy it for a second.

RULE 4 — NEVER LEAD WITH JARGON
Always state the concept in plain English first.
Introduce the technical term second, in parentheses or
as a natural follow-on.

BAD:  "Your RNOR status under Section 6(6) of the
       Income Tax Act determines..."
GOOD: "So here's the thing about moving back —
       there's actually a grace period called RNOR
       (Resident but Not Ordinarily Resident) where
       your foreign income stays tax-free for up to
       2 more years after you return. Think of it as
       a tax soft-landing."

RULE 5 — ALWAYS END WITH WHAT'S NEXT
Every response should either:
a) Ask the next question to build context, OR
b) Give the answer AND tell them exactly what to do next
Never leave the user floating without direction.

RULE 6 — KLIPY EMOTION TAGGING (MANDATORY)
At the end of EVERY response, output a JSON block.
This is parsed by the frontend to trigger GIFs/memes/stickers.
Always include it. Never skip it.

Format:
<klipy>
{
  "content_type": "gif" | "meme" | "sticker" | "clip" | "none",
  "query": "search query for KLIPY API",
  "intensity": "low" | "medium" | "high",
  "moment": "brief label for this emotional beat"
}
</klipy>

Content type selection logic:
- sticker → quick acknowledgments,
             processing moments, inline reactions
- gif     → emotional reactions,
             relief moments, energy shifts
- meme    → relatable pain/joy,
             universal human moments,
             big reveals
- clip    → peak celebration moments only,
             use maximum once per session
- none    → pure informational responses
             with no emotional beat

════════════════════════════════════════
ONBOARDING FLOW — INFORMATION GATHERING
════════════════════════════════════════

You need to gather context before you can help.
But it must feel like a conversation, not a KYC form.

Target information (collect naturally across 4-5 turns):
1. Current location / tax residency
2. Family situation (solo, married, dependents)
3. Income sources and rough portfolio size
4. Nature of the query (relocation / prize / freelance /
   inheritance / investment)
5. Prior tax awareness (have they filed before,
   do they know basic concepts)

Never ask for exact numbers upfront.
Ask for "ballpark" or "rough idea" —
users are more comfortable with approximations first.

WRONG opening: "Please provide your annual income,
                residential status, and nature of
                taxable event."
RIGHT opening:  "Hey! Before I can actually help,
                 just need to understand your situation
                 a bit. Where are you based right now?"

We are going to use the Vertex AI Memory Bank for the whole system and
Spanner Graph only for visualizing in the knowledge graph right now.
We can remove Spanner Graph if we don't need it in future.

════════════════════════════════════════
RESPONSE STRUCTURE RULES
════════════════════════════════════════

For INFORMATION GATHERING turns (first 4-5 messages):
- 2-3 sentences max
- One reaction + one question
- Light, conversational
- No tax content yet

For EXPLANATION turns:
- Lead with the plain English version
- One concept per message — don't dump everything at once
- Use analogies for complex concepts
- End with "want me to go deeper on this?"
  OR ask the next clarifying question

For CHECKLIST / ACTION PLAN turns:
- Use numbered list with emoji markers
- Each item max one line
- End with an energizing closing line,
  not a disclaimer

For CLARIFICATION turns (user is confused):
- Never say "as I mentioned earlier"
- Try a completely different angle or analogy
- Shorter sentences
- Ask "does that make more sense?"
  at the end — never assume

════════════════════════════════════════
WHAT YOU NEVER DO
════════════════════════════════════════

- Never say "I am just an AI and cannot provide
  legal/financial advice" mid-conversation.
  If liability disclaimer needed,
  say it ONCE at the very start naturally:
  "Obviously for the final call always loop in your CA,
   but let me give you the full picture first."

- Never use these phrases:
  "Certainly!" / "Absolutely!" / "Great question!" /
  "Of course!" / "I'd be happy to help!" —
  these sound like a customer service bot

- Never front-load with jargon —
  Section numbers come AFTER plain explanation

- Never ask more than one question per turn

- Never leave a turn without either asking
  what's next OR telling them what to do next

- Never make a user feel bad for not knowing
  basic tax concepts —
  this is specialized cross-border knowledge,
  normalize the confusion

- Never skip the <klipy> JSON block

════════════════════════════════════════
KLIPY TRIGGER REFERENCE
════════════════════════════════════════

Map these moments to content:

Session open          → sticker  → "welcome wave hi"
Big portfolio reveal  → meme     → "rich people problems we're not the same"
Tax shock moment      → meme     → "math lady calculating confused"
DTAA relief reveal    → gif      → "phew relief exhale relax"
Good news delivered   → gif      → "happy dance celebration"
Hackathon win         → gif      → "trophy winner champion"
Nobody warned them    → meme     → "this is fine dog fire"
Mind blown moment     → meme     → "galaxy brain mind blown"
Bullet dodged         → gif      → "dodged a bullet lucky"
Checklist delivered   → gif      → "mission accomplished checklist done"
Early retirement      → meme     → "retirement goals dream life"
Student tax anxiety   → sticker  → "don't worry got you"
Processing/thinking   → sticker  → "loading thinking"
Peak win moment       → clip     → "victory winning celebration"
Closing               → meme     → "legend we made it"

Intensity rules:
- low    → stickers, minor acknowledgments
- medium → gifs, moderate emotional beats
- high   → memes and clips,
           peak moments only (max 2 per session)

════════════════════════════════════════
MEMORY CONTEXT INJECTION
════════════════════════════════════════

At the start of each session, you will receive
a memory context block from Spanner Graph:

<memory_context>
  prior_sessions: int
  last_topic: string
  unresolved_queries: list
  user_profile: {
    jurisdiction: string,
    income_sources: list,
    tax_forms_discussed: list,
    awareness_level: "none" | "basic" | "intermediate"
  }
</memory_context>

If prior_sessions > 0:
- Reference the previous conversation naturally
- Pick up unresolved queries proactively
- Don't re-ask information you already have

If prior_sessions == 0:
- Fresh start, full onboarding flow
- Do NOT say "welcome back" or imply prior memory

Example returning user opening:
"Hey, welcome back! Last time we were going deep on
your NRE FD transition plan — did you manage to check
the maturity dates on those?
Because if any of them renew after your return date,
we have a problem to solve 😄"

════════════════════════════════════════
MULTIMODAL + SAFETY RULES
════════════════════════════════════════

You are connected to a multimodal session. YOU CAN SEE the user's camera feed directly.
When the user holds up documents (like Form 16, payslips, or receipts) or asks you to
"look at this", YOU CAN SEE IT. Do not tell them to upload it if you can see it clearly.
Answer tax questions clearly and concisely.
DO NOT under any circumstances output or narrate your internal thought process.
Do not say things like "Clarifying the inquiry" or "Adjusting my approach".
Just provide the direct answer to the user.
Do not restart with a welcome or introduction after reconnects.
Continue the current conversation naturally.
""".strip()

REAL_MODE_RULES = """
REAL MODE:
- Ask at most 5 short questions total to gather context.
- Prioritize: location, motive/goal, portfolio/savings, family, problem.
- After you have enough context, stop asking questions and move to action.
- Keep it warm, energetic, not robotic.
- Never say "welcome back" unless memory_context.prior_sessions > 0 AND memory_context.loaded is true.
""".strip()
def _format_klipy_block(kind: str, query: str) -> str:
    content_type = kind.lower()
    intensity = "low"
    if content_type in ("gif",):
        intensity = "medium"
    if content_type in ("meme", "clip"):
        intensity = "high"
    moment = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_") or "moment"
    payload = {
        "content_type": content_type,
        "query": query,
        "intensity": intensity,
        "moment": moment,
    }
    return "<klipy>\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n</klipy>"


def _pick_title(text: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("**Title:**"):
            return line.split("**Title:**", 1)[1].strip()
    for line in text.splitlines():
        if line.strip().startswith("## Post Title/Subject"):
            continue
        if line.strip().startswith("**\"") and line.strip().endswith("\"**"):
            return line.strip().strip("*").strip('"')
    for line in text.splitlines():
        if line.strip().startswith("OVERVIEW"):
            return "TurboTax capital gains overview"
    return "Tax evidence"


def _pick_date(text: str) -> str:
    for line in text.splitlines():
        if "Date Asked:" in line:
            return line.split("Date Asked:", 1)[1].strip()
        if "Post Date:" in line:
            return line.split("Post Date:", 1)[1].strip()
    return ""


def _pick_snippet(text: str, max_len: int = 280) -> str:
    candidates = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("URL :") or clean.startswith("##") or clean.startswith("**"):
            continue
        if clean.lower().startswith("answer") or clean.lower().startswith("content:"):
            continue
        candidates.append(clean)
        if len(" ".join(candidates)) > max_len:
            break
    snippet = " ".join(candidates).strip()
    if len(snippet) > max_len:
        snippet = snippet[: max_len - 3].rstrip() + "..."
    return snippet


_INTERNAL_AGENT_MARKERS = (
    "my next step",
    "i'm focusing",
    "i am focusing",
    "i'm currently focused",
    "i am currently focused",
    "i've noted",
    "i have noted",
    "i've acknowledged",
    "i have acknowledged",
    "i need to",
    "i'll ask",
    "i will ask",
    "to offer tax advice",
    "clarifying tax inquiry",
    "clarifying the query",
    "clarifying the inquiry",
    "acknowledge and inquire",
    "determining tax implications",
    "addressing the form 16 inquiry",
    "addressing the",
)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _sanitize_greeting(text: str, state: SessionState) -> str:
    if not text:
        return text
    memory = state.memory_context or {}
    if memory.get("loaded") and int(memory.get("prior_sessions", 0)) > 0:
        return text
    return re.sub(r"(?i)\bwelcome back\b", "Hey", text)


def _strip_tool_failures(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(
        r"I could not retrieve usable tax evidence.*?(?:\\.|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split()).strip()


def _strip_klipy_from_text(text: str) -> str:
    if not text:
        return text
    return re.sub(r"<klipy>[\s\S]*?(?:</klipy>|</kl_y>|$)", "", text, flags=re.IGNORECASE).strip()


def _is_low_quality_agent_text(text: str) -> bool:
    clean_text = _normalize_text(text)
    if not clean_text:
        return True

    lowered = clean_text.lower()
    if clean_text.startswith("**"):
        return True

    if any(marker in lowered for marker in _INTERNAL_AGENT_MARKERS):
        return True

    if re.match(r"^advisor:\s*\*\*", lowered):
        return True

    if any(
        phrase in lowered
        for phrase in (
            "my initial assessment",
            "i will respond",
            "i will transition",
            "i acknowledge the user's",
            "i acknowledge the user",
            "i'm confirming",
            "i am confirming",
            "i'm ready to assist",
            "i am ready to assist",
        )
    ):
        return True

    return False


def _select_final_agent_text(raw_text: str, tool_answer: str) -> str:
    clean_tool_answer = _normalize_text(tool_answer)
    if clean_tool_answer:
        return clean_tool_answer

    clean_raw_text = _normalize_text(raw_text)
    if not clean_raw_text or _is_low_quality_agent_text(clean_raw_text):
        return ""

    return clean_raw_text


def _is_voiced_audio_chunk(b64_data: str, threshold: int = 450) -> bool:
    try:
        raw = base64.b64decode(b64_data)
    except Exception:
        return False

    if len(raw) < 4:
        return False

    pcm = array("h")
    pcm.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not pcm:
        return False

    peak = 0
    step = max(1, len(pcm) // 64)
    for idx in range(0, len(pcm), step):
        sample = abs(pcm[idx])
        if sample > peak:
            peak = sample
            if peak >= threshold:
                return True

    return False


def _websocket_connected(websocket: WebSocket) -> bool:
    return websocket.client_state == WebSocketState.CONNECTED


def _save_agent_results(
    *,
    state: SessionState,
    query: str,
    content: dict[str, Any],
) -> None:
    try:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(data_dir, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": state.user_id,
            "session_id": state.session_id,
            "query": query,
            "sources": content.get("sources", []),
            "source_statuses": content.get("source_statuses", []),
            "claims": content.get("claims", []),
        }
        out_path = os.path.join(data_dir, "agent_results.jsonl")
        with open(out_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("agent_results_write_failed", error=str(exc))


async def _safe_send_json(
    websocket: WebSocket,
    payload: dict[str, Any],
    *,
    log_key: str = "websocket_send_not_deliverable",
    **log_ctx: Any,
) -> bool:
    if not _websocket_connected(websocket):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError) as exc:
        logger.warning(log_key, error=str(exc), **log_ctx)
        return False


def _append_ephemeral_turn(state: SessionState, role: str, text: str) -> None:
    clean_text = _normalize_text(text)
    if not clean_text:
        return

    turns = state.turns
    if turns and turns[-1].get("role") == role and turns[-1].get("text") == clean_text:
        return

    turns.append({"role": role, "text": clean_text})
    if len(turns) > 10:
        del turns[:-10]
    state.touch()


def _build_ephemeral_memory_prompt(state: SessionState) -> str:
    turns = state.turns or []
    if not turns:
        return ""

    serialized = []
    for turn in turns[-6:]:
        role = "User" if turn.get("role") == "user" else "Advisor"
        text = _normalize_text(turn.get("text") or "")
        if text:
            serialized.append(f"{role}: {text[:220]}")

    if not serialized:
        return ""

    return "CURRENT SESSION CONTEXT:\n" + "\n".join(serialized)


def _extract_location_hint(text: str) -> str | None:
    clean = _normalize_text(text).lower()
    if not clean:
        return None
    if "india" in clean or "bharat" in clean:
        return "India"
    if "united states" in clean or "u.s." in clean or "usa" in clean or "america" in clean:
        return "United States"
    if "uk" in clean or "united kingdom" in clean or "england" in clean:
        return "United Kingdom"
    if "canada" in clean:
        return "Canada"
    if "australia" in clean:
        return "Australia"
    return None


def _update_user_context(state: SessionState, text: str) -> None:
    clean = _normalize_text(text).lower()
    if not clean:
        return
    ctx = state.user_context

    if "india" in clean or "bharat" in clean:
        ctx.setdefault("location", "India")
    if "us" in clean or "u.s." in clean or "united states" in clean or "america" in clean:
        ctx.setdefault("location", "USA")
    if "uk" in clean or "united kingdom" in clean:
        ctx.setdefault("location", "UK")

    if "move" in clean or "relocat" in clean or "return" in clean:
        ctx.setdefault("motive", "relocation")
    if "retire" in clean:
        ctx.setdefault("motive", "retirement")

    if "wife" in clean or "husband" in clean or "son" in clean or "daughter" in clean or "family" in clean:
        ctx.setdefault("family", "yes")
    if "solo" in clean or "just me" in clean or "only me" in clean:
        ctx.setdefault("family", "no")

    if "ibkr" in clean or "interactive brokers" in clean or "etf" in clean or "equities" in clean or "stocks" in clean:
        ctx.setdefault("portfolio", "market investments")
    if "crore" in clean or "cr" in clean or "₹" in clean or "$" in clean or "million" in clean or "lakhs" in clean:
        ctx.setdefault("portfolio", "mentioned")
    if "nre" in clean or "fd" in clean or "fixed deposit" in clean:
        ctx.setdefault("nre_fd", "present")

    if "tax" in clean or "itr" in clean or "ltcg" in clean:
        ctx.setdefault("problem", "tax planning")
    if "prize" in clean or "hackathon" in clean:
        ctx.setdefault("problem", "international prize")
    if "invest" in clean or "portfolio" in clean:
        ctx.setdefault("problem", ctx.get("problem", "investments"))

    if "not" in clean and "tax" in clean or "no" in clean and "tax" in clean:
        ctx.setdefault("awareness_level", "none")

    state.user_context = ctx


def _context_ready(state: SessionState) -> bool:
    ctx = state.user_context
    required = {"location", "motive", "portfolio", "problem"}
    return required.issubset(set(ctx.keys()))


def _build_query_builder_payload(state: SessionState) -> dict[str, Any]:
    ctx = state.user_context.copy()
    ctx.setdefault("jurisdiction", "cross-border" if ctx.get("location") else "unknown")
    return ctx


def _build_agent_queries(state: SessionState) -> dict[str, str]:
    ctx = state.user_context
    location = ctx.get("location", "India")
    motive = ctx.get("motive", "tax planning")
    problem = ctx.get("problem", "tax planning")
    portfolio = ctx.get("portfolio", "investments")
    base = f"{location} {motive} {problem} {portfolio}"
    # Keep queries short and search-like
    return {
        "caclub_india": f"NRI return India RNOR 182 days {base}",
        "taxtmi": "NRE FD taxability resident status change",
        "turbotax_blog": "US India DTAA capital gains nonresident exit",
        "taxprofblog": "IBKR portfolio India relocation tax strategy",
    }




def _compose_system_instruction(
    state: SessionState,
    persistent_memory_prompt: str = "",
    proactive_prompt: str = "",
    memory_context: dict[str, Any] | None = None,
) -> str:
    blocks = [BASE_SYSTEM_INSTRUCTION, REAL_MODE_RULES]

    if persistent_memory_prompt:
        blocks.append(f"HISTORICAL MEMORY:\n{persistent_memory_prompt}")

    if memory_context:
        prior_sessions = memory_context.get("prior_sessions", 0)
        loaded = memory_context.get("loaded", False)
        summary = memory_context.get("summary", "")
        recent_turns = memory_context.get("recent_turns", [])
        blocks.append(
            "MEMORY_CONTEXT:\n"
            f"- prior_sessions: {prior_sessions}\n"
            f"- loaded: {loaded}\n"
            f"- summary: {summary}\n"
            f"- recent_turns: {recent_turns}"
        )

    ephemeral_prompt = _build_ephemeral_memory_prompt(state)
    if ephemeral_prompt:
        blocks.append(ephemeral_prompt)

    if proactive_prompt:
        blocks.append(f"BACKGROUND TAX PROFILE:\n{proactive_prompt}")

    return "\n\n".join(block for block in blocks if block).strip()


def _frontend_memory_context(context: dict[str, Any]) -> dict[str, Any]:
    raw_topics = context.get("top_topics", []) or context.get("prior_topics", []) or []
    prior_topics = [
        topic.get("topic", "")
        if isinstance(topic, dict)
        else str(topic)
        for topic in raw_topics
    ]
    prior_topics = [topic for topic in prior_topics if topic]
    prior_sessions = context.get("prior_sessions")
    if prior_sessions is None:
        # Fallback to 0 when the memory backend doesn't provide it.
        prior_sessions = 0
    return {
        "summary": context.get("summary", ""),
        "recent_turns": context.get("recent_turns", []) or [],
        "prior_topics": prior_topics,
        "prior_sessions": int(prior_sessions),
        "loaded": bool(context.get("loaded")),
        "prompt": context.get("prompt", ""),
    }


async def _load_conversation_memory_context(user_id: str) -> dict[str, Any]:
    try:
        context = await get_memory_service().load_conversation_context(user_id=user_id)
        return _frontend_memory_context(context)
    except Exception as exc:
        logger.warning("conversation_memory_context_failed", user_id=user_id, error=str(exc))
        return _frontend_memory_context({})


async def _persist_turn(
    *,
    state: SessionState,
    role: str,
    text: str,
    refresh_summary: bool = False,
) -> None:
    clean_text = _normalize_text(text)
    if not clean_text:
        return

    try:
        turn_id = await get_memory_service().append_turn(
            user_id=state.user_id,
            session_id=state.session_id,
            role=role,
            text=clean_text,
        )
        persist_turn_to_obsidian(
            user_id=state.user_id,
            session_id=state.session_id,
            role=role,
            text=clean_text,
            turn_id=turn_id,
        )
        await get_memory_service().enqueue_turn_memory(
            user_id=state.user_id,
            session_id=state.session_id,
            role=role,
            text=clean_text,
            turn_id=turn_id,
        )
        if refresh_summary:
            await get_memory_service().enqueue_summary_refresh(
                user_id=state.user_id,
                session_id=state.session_id,
            )
        state.last_memory_write_status = "ok"
        state.touch()
    except SqlPersistenceError as exc:
        state.last_memory_write_status = f"sql_error:{exc}"
        state.last_error = str(exc)
        state.touch()
        logger.warning(
            "conversation_turn_store_failed",
            user_id=state.user_id,
            session_id=state.session_id,
            role=role,
            error=str(exc),
        )
    except Exception as exc:
        state.last_memory_write_status = f"error:{exc}"
        state.last_error = str(exc)
        state.touch()
        logger.warning(
            "conversation_turn_store_failed",
            user_id=state.user_id,
            session_id=state.session_id,
            role=role,
            error=str(exc),
        )


def _schedule_turn_persist(
    *,
    state: SessionState,
    role: str,
    text: str,
    refresh_summary: bool = False,
) -> None:
    asyncio.create_task(
        _persist_turn(
            state=state,
            role=role,
            text=text,
            refresh_summary=refresh_summary,
        )
    )



class GeminiLiveProxy:
    def __init__(self):
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        from google import genai
        # v1alpha is required for preview Live API models like
        # gemini-2.5-flash-native-audio-dialog (not available on v1beta default)
        self.client = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options={"api_version": "v1alpha"},
        )
        self.active_session = None
        self._session_cm = None
        self.session_alive = False  # True only when Gemini session is confirmed active
        self._resumption_handle: Optional[str] = None

    async def connect(
        self,
        session_id: str,
        system_instruction: str = (
            "You are a helpful tax advisor assistant. "
            "When greeting a user proactively, keep it brief and friendly."
        ),
        voice_name: str = "Aoede",
        response_modalities: list = None,
    ):
        """Connect to Gemini Live API

        Args:
            session_id: Unique session identifier.
            system_instruction: System prompt for the agent.
            voice_name: Voice name for speech output (e.g. Aoede, Puck, Charon).
            response_modalities: List of response types, e.g. ["AUDIO"] or ["TEXT"].
        """
        if response_modalities is None:
            response_modalities = ["AUDIO"]

        # Store config for auto-reconnect
        self._last_session_id = session_id
        self._last_system_instruction = system_instruction
        self._last_voice_name = voice_name
        self._last_response_modalities = response_modalities

        try:
            # Build the connect config.
            # NOTE: context_window_compression and session_resumption with a
            # null handle both cause 1007 on gemini-2.0-flash-live-001 — only
            # include session_resumption when we actually have a prior handle.
            live_config: dict = {
                "system_instruction": system_instruction,
                "response_modalities": response_modalities,
                "input_audio_transcription": {},
                "output_audio_transcription": {},
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": voice_name
                        }
                    }
                },
                "tools": [{"function_declarations": [{
                    "name": "ask_geo_router",
                    "description": (
                        "Forward the user's explicit tax query to the Geo Router, "
                        "which will delegate to the correct India or USA tax clusters "
                        "to calculate tax liability or strategies."
                    ),
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "tax_query": {
                                "type": "STRING",
                                "description": "The specific tax question, numbers, or forms to evaluate."
                            }
                        },
                        "required": ["tax_query"]
                    }
                }]}],
            }

            # Only include session resumption when we have an actual handle
            if self._resumption_handle:
                live_config["session_resumption"] = {"handle": self._resumption_handle}

            logger.info("gemini_live_connect_payload", config=live_config)

            self._session_cm = self.client.aio.live.connect(
                model=VOICE_MODEL,
                config=live_config,
            )

            self.active_session = await self._session_cm.__aenter__()
            self.session_alive = True
            return self.active_session
        except Exception as e:
            logger.error("failed_to_connect_to_gemini_live", error=str(e))
            raise

    async def reconnect(self):
        """Reconnect using the same config as the last connect() call."""
        await self.close()
        return await self.connect(
            self._last_session_id,
            system_instruction=self._last_system_instruction,
            voice_name=self._last_voice_name,
            response_modalities=self._last_response_modalities,
        )

    async def send_audio_b64(self, b64_data: str):
        """Send base64-encoded audio directly to Gemini Live.

        Accepts the base64 string straight from the frontend so we
        skip the unnecessary decode→re-encode cycle.
        MIME type includes sample rate which is REQUIRED by the
        native-audio model — without it the session drops with 1011.
        """
        if not self.active_session or not self.session_alive:
            return  # silently drop — session is dead
        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception:
            return
        await self.active_session.send_realtime_input(
            audio={"mime_type": "audio/pcm;rate=16000", "data": raw_bytes}
        )

    async def send_video_b64(self, b64_data: str):
        """Send base64-encoded video frame directly to Gemini Live."""
        if not self.active_session or not self.session_alive:
            return
        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception:
            return
            
        await self.active_session.send_realtime_input(
            video={"mime_type": "image/jpeg", "data": raw_bytes}
        )

    async def send_text(self, text: str):
        """
        Send a text input to Gemini Live.

        Note: send_client_content is NOT supported by gemini-2.5-flash-native-audio-latest.
        The native-audio model only accepts send_realtime_input. Using send_client_content
        causes the Gemini WS to enter an unexpected state and then drop with 1011 keepalive
        timeout when the next audio frame arrives.
        """
        if not self.active_session or not self.session_alive:
            raise RuntimeError("Not connected to Gemini Live")
        await self.active_session.send_realtime_input(text=text)

    async def receive_response(self) -> AsyncGenerator[dict, None]:
        """Receive response stream from Gemini Live"""
        if not self.active_session:
            raise RuntimeError("Not connected to Gemini Live")
        async for response in self.active_session.receive():
            yield response

    async def close(self):
        """Close the Gemini Live session"""
        self.session_alive = False
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.error("error_during_close", error=str(e))
            self._session_cm = None
            self.active_session = None


async def _forward_gemini_responses(
    proxy: GeminiLiveProxy,
    websocket: WebSocket,
    state: SessionState,
):
    """
    Background asyncio.Task — continuously reads responses from Gemini Live
    and forwards audio, text, and control events to the browser WebSocket.

    Includes auto-reconnect: if the Gemini session times out (keepalive
    or inactivity), this function reconnects and resumes listening.
    """
    current_agent_chunks: list[str] = []
    current_user_chunks: list[str] = []
    try:
        async for response in proxy.receive_response():
            if not _websocket_connected(websocket):
                return

            server_content = getattr(response, "server_content", None)
            if server_content:
                if getattr(server_content, "interrupted", False):
                    current_agent_chunks = []
                    current_user_chunks = []
                    state.last_tool_answer = ""
                    state.pending_tool_answer = ""
                    state.touch()
                    await _safe_send_json(websocket, {"type": "interrupted"})

                if getattr(server_content, "turn_complete", False):
                    finalized_user_text = _normalize_text("".join(current_user_chunks))
                    if finalized_user_text and finalized_user_text != state.last_user_text:
                        _append_ephemeral_turn(state, "user", finalized_user_text)
                        _update_user_context(state, finalized_user_text)
                        location_hint = _extract_location_hint(finalized_user_text)
                        if location_hint and location_hint not in state.proactive_prompt:
                            state.proactive_prompt = (
                                (state.proactive_prompt + "\n" if state.proactive_prompt else "")
                                + f"Known user location: {location_hint}."
                                + " Do not ask again unless the user indicates a move."
                            )
                        _schedule_turn_persist(
                            state=state,
                            role="user",
                            text=finalized_user_text,
                        )
                        state.last_user_text = finalized_user_text
                        state.current_topics = (state.current_topics + [finalized_user_text[:120]])[-6:]
                        state.touch()
                    current_user_chunks = []
                    if not state.context_dispatched and _context_ready(state):
                        state.context_dispatched = True
                        state.touch()
                        await _safe_send_json(websocket, {
                            "type": "tool_call",
                            "name": "query_builder",
                            "args": _build_query_builder_payload(state),
                        })
                        await _safe_send_json(websocket, {
                            "type": "tool_call",
                            "name": "dispatch_agents",
                            "args": _build_agent_queries(state),
                        })
                        await _safe_send_json(websocket, {"type": "thinking"})
                        query = " ".join(_build_agent_queries(state).values())[:200]
                        routing_result = await process_voice_query(
                            query,
                            user_id=state.user_id,
                            session_id=state.session_id,
                        )
                        content = routing_result.get("content", {})
                        synthesized = content.get("synthesized_response") or str(routing_result)
                        synthesized = _strip_tool_failures(_sanitize_greeting(synthesized, state))
                        _save_agent_results(state=state, query=query, content=content)
                        await _safe_send_json(websocket, {"type": "content", "content": content})
                        await _safe_send_json(websocket, {
                            "type": "tool_call",
                            "name": "agent_status",
                            "args": {"statuses": content.get("source_statuses", [])},
                        })
                        await _safe_send_json(websocket, {"type": "text", "text": synthesized})
                        await _safe_send_json(websocket, {"type": "turnComplete"})
                    finalized_agent_text = _select_final_agent_text(
                        "".join(current_agent_chunks),
                        str(state.last_tool_answer),
                    )
                    if (
                        finalized_agent_text
                        and finalized_agent_text != state.last_agent_text
                    ):
                        _append_ephemeral_turn(state, "agent", finalized_agent_text)
                        _schedule_turn_persist(
                            state=state,
                            role="agent",
                            text=finalized_agent_text,
                            refresh_summary=True,
                        )
                        state.last_agent_text = finalized_agent_text
                        state.current_topics = (state.current_topics + [finalized_agent_text[:120]])[-6:]
                        state.touch()
                    current_agent_chunks = []
                    state.last_tool_answer = ""
                    state.pending_tool_answer = ""
                    state.touch()
                    await _safe_send_json(websocket, {"type": "turnComplete"})

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn:
                    for part in getattr(model_turn, "parts", []):
                        part_text = getattr(part, "text", None)
                        if part_text:
                            current_agent_chunks.append(part_text)
                            if not _is_low_quality_agent_text(part_text):
                                await _safe_send_json(websocket, {
                                    "type": "text",
                                    "text": part_text,
                                })

                        inline_data = getattr(part, "inline_data", None)
                        if inline_data:
                            audio_b64 = getattr(inline_data, "data", None)
                            if audio_b64 is not None:
                                if isinstance(audio_b64, bytes):
                                    audio_b64 = base64.b64encode(audio_b64).decode("utf-8")
                                await _safe_send_json(websocket, {
                                    "type": "audio",
                                    "data": audio_b64,
                                })

                input_tx = getattr(server_content, "input_transcription", None)
                if input_tx:
                    input_text = (
                        getattr(input_tx, "text", None)
                        or getattr(input_tx, "content", None)
                        or str(input_tx)
                    )
                    if input_text:
                        current_user_chunks.append(input_text)
                        await _safe_send_json(websocket, {
                            "type": "input_transcription",
                            "content": input_text,
                            "finished": getattr(input_tx, "finished", True),
                        })

                output_tx = getattr(server_content, "output_transcription", None)
                if output_tx:
                    output_text = (
                        getattr(output_tx, "text", None)
                        or getattr(output_tx, "content", None)
                        or str(output_tx)
                    )
                    if output_text:
                        output_text = _sanitize_greeting(output_text, state)
                        await _safe_send_json(websocket, {
                            "type": "output_transcription",
                            "content": output_text,
                            "finished": getattr(output_tx, "finished", True),
                        })

            resumption_update = getattr(response, "session_resumption_update", None)
            if resumption_update:
                new_handle = getattr(resumption_update, "new_handle", None) or getattr(resumption_update, "handle", None)
                if new_handle:
                    proxy._resumption_handle = new_handle
                    SESSION_HANDLES[proxy._last_session_id] = new_handle
                    logger.info("session_resumption_handle_updated", session_id=proxy._last_session_id)

            input_tx = getattr(response, "input_transcription", None)
            if input_tx:
                input_text = (
                    getattr(input_tx, "text", None)
                    or getattr(input_tx, "content", None)
                    or str(input_tx)
                )
                if input_text:
                    current_user_chunks.append(input_text)
                    await _safe_send_json(websocket, {
                        "type": "input_transcription",
                        "content": input_text,
                        "finished": getattr(input_tx, "finished", True),
                    })

            output_tx = getattr(response, "output_transcription", None)
            if output_tx:
                output_text = (
                    getattr(output_tx, "text", None)
                    or getattr(output_tx, "content", None)
                    or str(output_tx)
                )
                if output_text:
                    output_text = _sanitize_greeting(output_text, state)
                    await _safe_send_json(websocket, {
                        "type": "output_transcription",
                        "content": output_text,
                        "finished": getattr(output_tx, "finished", True),
                    })

            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                for call in getattr(tool_call, "function_calls", []):
                    if call.name != "ask_geo_router":
                        continue

                    args = getattr(call, "args", {}) or {}
                    query = args.get("tax_query", "")
                    logger.info("tool_call", function="ask_geo_router", tax_query=query)

                    if query and query != state.last_user_text:
                        _append_ephemeral_turn(state, "user", query)
                        _schedule_turn_persist(
                            state=state,
                            role="user",
                            text=query,
                        )
                        state.last_user_text = query
                        state.current_topics = (state.current_topics + [query[:120]])[-6:]
                        state.touch()

                    await _safe_send_json(websocket, {"type": "user_text", "text": query})
                    await _safe_send_json(websocket, {"type": "thinking"})
                    routing_result = await process_voice_query(
                        query,
                        user_id=state.user_id,
                        session_id=state.session_id,
                    )
                    answer = routing_result.get("content", {}).get(
                        "synthesized_response",
                        str(routing_result),
                    )
                    state.last_tool_answer = _normalize_text(answer)
                    state.pending_tool_answer = state.last_tool_answer
                    state.touch()

        proxy.session_alive = False
        logger.warning("gemini_live_session_ended")
    except asyncio.CancelledError:
        logger.info("response_forwarding_task_cancelled")
        return
    except Exception as e:
        proxy.session_alive = False
        logger.error("response_forwarding_error", error=str(e))


def create_websocket_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.get("/debug/session-cache")
    async def session_cache_debug():
        return {
            **SESSION_STATE_STORE.stats(),
            "sessions": SESSION_STATE_STORE.snapshot(),
        }

    @app.get("/debug/memory")
    async def memory_debug():
        return await get_memory_service().debug_status()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        proxy = GeminiLiveProxy()
        session_id = "default"
        user_id = "anonymous"
        response_task: Optional[asyncio.Task] = None
        reconnect_lock = asyncio.Lock()
        explicit_stop = False
        state = SESSION_STATE_STORE.get_or_create(user_id, session_id)

        async def ensure_live_session(reason: str) -> bool:
            nonlocal response_task

            if proxy.session_alive and proxy.active_session:
                return True

            async with reconnect_lock:
                if proxy.session_alive and proxy.active_session:
                    return True

                try:
                    proxy._last_system_instruction = _compose_system_instruction(
                        state,
                        persistent_memory_prompt=state.persistent_memory_prompt,
                        proactive_prompt=state.proactive_prompt,
                        memory_context=state.memory_context,
                    )
                    await proxy.reconnect()
                    state.last_reconnect_reason = reason
                    state.touch()

                    if response_task and not response_task.done():
                        response_task.cancel()
                        try:
                            await response_task
                        except asyncio.CancelledError:
                            pass

                    response_task = asyncio.create_task(
                        _forward_gemini_responses(proxy, websocket, state)
                    )

                    await _safe_send_json(
                        websocket,
                        {"type": "reconnected"},
                        log_key="reconnect_notice_not_deliverable",
                        reason=reason,
                    )
                    logger.info("gemini_session_reconnected", reason=reason)
                    return True
                except Exception as exc:
                    logger.error("reconnect_attempt_failed", reason=reason, error=str(exc))
                    await _safe_send_json(
                        websocket,
                        {"type": "error", "message": f"Session reconnect failed: {exc}"},
                        log_key="reconnect_error_not_deliverable",
                        reason=reason,
                        error=str(exc),
                    )
                    return False

        try:
            session_started = False
            while True:
                if not _websocket_connected(websocket):
                    break
                try:
                    raw_message = await websocket.receive_text()
                except WebSocketDisconnect:
                    raise
                except RuntimeError as exc:
                    logger.info("websocket_receive_closed", error=str(exc))
                    break
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    await _safe_send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type")

                # ── Session start ─────────────────────────────────────────
                if msg_type == "start" and not session_started:
                    try:
                        session_id = data.get("session_id", "default")
                        user_id = data.get("user_id", "anonymous")
                        state = SESSION_STATE_STORE.get_or_create(user_id, session_id)
                        # Read user-chosen config from the frontend SettingsDialog
                        voice_name = data.get("voice", "Aoede")
                        response_modalities = data.get("response_modalities", ["AUDIO"])
                        
                        # Fix #2: Gemini 2.5 native audio models crash with 1007 if "TEXT" is included
                        # Forcing it to just AUDIO.
                        if "TEXT" in response_modalities:
                            response_modalities.remove("TEXT")
                        if not response_modalities:
                            response_modalities = ["AUDIO"]

                        conversation_memory = await _load_conversation_memory_context(user_id)
                        if not state.persistent_memory_prompt:
                            state.persistent_memory_prompt = conversation_memory.get("prompt", "")
                        if conversation_memory.get("prior_topics"):
                            state.current_topics = list(conversation_memory.get("prior_topics", []))[:6]
                        state.memory_context = conversation_memory
                        state.touch()

                        system_instruction = _compose_system_instruction(
                            state,
                            persistent_memory_prompt=state.persistent_memory_prompt,
                            proactive_prompt=state.proactive_prompt,
                            memory_context=conversation_memory,
                        )

                        # Try to resume conversation if we have a cached handle
                        cached_handle = SESSION_HANDLES.get(session_id)
                        if cached_handle:
                            proxy._resumption_handle = cached_handle
                            logger.info("resuming_previous_session", session_id=session_id)

                        await proxy.connect(
                            session_id,
                            system_instruction=system_instruction,
                            voice_name=voice_name,
                            response_modalities=response_modalities,
                        )
                        session_started = True

                        await _safe_send_json(websocket, {"type": "connected"})
                        await _safe_send_json(
                            websocket,
                            {"type": "memory_context", "memory_context": {
                                "summary": conversation_memory.get("summary", ""),
                                "recent_turns": conversation_memory.get("recent_turns", []),
                                "prior_topics": conversation_memory.get("prior_topics", []),
                                "prior_sessions": conversation_memory.get("prior_sessions", 0),
                                "loaded": conversation_memory.get("loaded", False),
                            }},
                        )

                        response_task = asyncio.create_task(
                            _forward_gemini_responses(proxy, websocket, state)
                        )


                    except Exception as exc:
                        logger.error("session_start_failed", error=str(exc), exc_info=True)
                        try:
                            await _safe_send_json(websocket, {"type": "error", "message": str(exc)})
                        except Exception:
                            logger.warning("session_start_error_not_deliverable", error=str(exc))
                        continue

                # ── Audio stream from browser mic ─────────────────────────
                elif msg_type == "audio":
                    if not session_started or not proxy.session_alive:
                        if not session_started:
                            continue
                        if not _is_voiced_audio_chunk(data["data"]):
                            continue
                        if not await ensure_live_session("audio"):
                            continue
                    try:
                        await proxy.send_audio_b64(data["data"])
                    except Exception as exc:
                        proxy.session_alive = False
                        logger.warning("audio_send_failed", error=str(exc))
                        await _safe_send_json(websocket, {"type": "error", "message": f"Audio send failed: {exc}"})

                # ── Video frame from browser camera ───────────────────────
                elif msg_type == "video":
                    if not session_started or not proxy.session_alive:
                        continue
                    try:
                        await proxy.send_video_b64(data["data"])
                    except Exception as exc:
                        proxy.session_alive = False
                        logger.warning("video_send_failed", error=str(exc))

                # ── Text message from chat panel ──────────────────────────
                elif msg_type == "text":
                    if not session_started:
                        await _safe_send_json(websocket, {"type": "error", "message": "Session not started"})
                        continue
                    try:
                        text = data.get("text", "")
                        if not proxy.session_alive and not await ensure_live_session("text"):
                            continue
                        await proxy.send_text(text)
                        clean_text = _normalize_text(text)
                        if clean_text:
                            _append_ephemeral_turn(state, "user", clean_text)
                            _schedule_turn_persist(
                                state=state,
                                role="user",
                                text=clean_text,
                            )
                            state.last_user_text = clean_text
                            state.current_topics = (state.current_topics + [clean_text[:120]])[-6:]
                            state.touch()
                    except Exception as exc:
                        logger.error("text_send_failed", error=str(exc))
                        await _safe_send_json(websocket, {"type": "error", "message": f"Text send failed: {exc}"})

                # ── Interrupt (user speaking over AI) ─────────────────────
                elif msg_type == "interrupt":
                    try:
                        if response_task and not response_task.done():
                            response_task.cancel()
                        await proxy.close()
                        await _safe_send_json(websocket, {"type": "interrupted"})
                        # Reconnect for next turn
                        proxy._last_system_instruction = _compose_system_instruction(
                            state,
                            persistent_memory_prompt=state.persistent_memory_prompt,
                            proactive_prompt=state.proactive_prompt,
                            memory_context=state.memory_context,
                        )
                        await ensure_live_session("interrupt")
                    except Exception as exc:
                        logger.error("interrupt_failed", error=str(exc))

                # ── Stop session ──────────────────────────────────────────
                elif msg_type == "stop":
                    explicit_stop = True
                    if response_task and not response_task.done():
                        response_task.cancel()
                    await proxy.close()
                    await _safe_send_json(websocket, {"type": "stopped"})
                    SESSION_STATE_STORE.delete(user_id, session_id)
                    break

        except WebSocketDisconnect:
            logger.info("websocket_client_disconnected")
        except Exception as exc:
            logger.error("websocket_handler_error", error=str(exc), exc_info=True)
            await _safe_send_json(
                websocket,
                {"type": "error", "message": str(exc)},
                log_key="websocket_error_not_deliverable",
                error=str(exc),
            )
        finally:
            if response_task and not response_task.done():
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass
            await proxy.close()
            if explicit_stop:
                SESSION_STATE_STORE.delete(user_id, session_id)

    return app


# Module-level app export so `uvicorn backend.websocket_server:app` works
app = create_websocket_app()


# ── Standalone run for testing / direct launch ─────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")


# ── Voice + Geo Router Integration ────────────────────────────────────────────
async def process_voice_query(
    transcribed_text: str,
    user_id: str = "anonymous",
    session_id: str = "default",
) -> dict:
    """Process transcribed text through the shared live orchestrator."""
    try:
        return await run_live_query(
            transcribed_text,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning("live_query_orchestration_failed", error=str(exc))
        try:
            from agents.adk.geo_router.agent import keyword_based_routing
            routing_info = await keyword_based_routing(transcribed_text)
            jurisdiction = routing_info.get("jurisdiction", "tax")
            return {
                "routing": routing_info,
                "content": {
                    "query": transcribed_text,
                    "sources": [],
                    "claims": [],
                    "contradictions": [],
                    "jurisdiction": jurisdiction,
                    "synthesized_response": (
                        f"Your query seems to be related to {jurisdiction} jurisdiction. "
                        "Please ask a more specific tax question."
                    ),
                },
            }
        except Exception:
            return {
                "content": {
                    "query": transcribed_text,
                    "sources": [],
                    "claims": [],
                    "contradictions": [],
                    "jurisdiction": "both",
                    "synthesized_response": (
                        "I couldn't process your query through the tax routing system. "
                        "Please ask your tax question directly."
                    ),
                },
            }
