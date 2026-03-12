"""Centralized configuration for TaxAgent.

Loads environment variables from .env via python-dotenv and exposes
typed constants used throughout the application. Every agent, backend
service, and memory module should import from here rather than calling
os.getenv() directly.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Service URLs (inter-agent communication)
# ---------------------------------------------------------------------------
CACLUB_AGENT_URL = os.getenv("CACLUB_AGENT_URL", "http://localhost:8001")
TAXTMI_AGENT_URL = os.getenv("TAXTMI_AGENT_URL", "http://localhost:8002")
TURBOTAX_AGENT_URL = os.getenv("TURBOTAX_AGENT_URL", "http://localhost:8005")
TAXPROFBLOG_AGENT_URL = os.getenv("TAXPROFBLOG_AGENT_URL", "http://localhost:8004")
ROOT_AGENT_URL = os.getenv("ROOT_AGENT_URL", "http://localhost:8000")
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL", "http://localhost:8003")
GRAPH_API_URL = os.getenv("GRAPH_API_URL", "http://localhost:8006")
GRAPH_API_PORT = int(os.getenv("GRAPH_API_PORT", "8006"))

# ---------------------------------------------------------------------------
# Model names
# ---------------------------------------------------------------------------
# Text agents — Gemini 3.1 Flash Lite Preview (4/500 RPD — verified available)
SOURCE_AGENT_MODEL = os.getenv("SOURCE_AGENT_MODEL", "gemini-3.1-flash-lite-preview")
ROOT_AGENT_MODEL = os.getenv("ROOT_AGENT_MODEL", "gemini-3.1-flash-lite-preview")
GEO_ROUTER_MODEL = os.getenv("GEO_ROUTER_MODEL", "gemini-3.1-flash-lite-preview")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gemini-3.1-flash-lite-preview")

# Voice — Gemini Live native audio model for bidi audio + video.
VOICE_MODEL = os.getenv("VOICE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")

# ---------------------------------------------------------------------------
# Shared secrets
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# ---------------------------------------------------------------------------
# Spanner configuration
# ---------------------------------------------------------------------------
SPANNER_PROJECT_ID = os.getenv("SPANNER_PROJECT_ID", "newproject-489516")
SPANNER_INSTANCE_ID = os.getenv("SPANNER_INSTANCE_ID", "taxclarity-free")
SPANNER_DATABASE_ID = os.getenv("SPANNER_DATABASE_ID", "taxclarity")
SPANNER_INSTANCE_CONFIG = os.getenv("SPANNER_INSTANCE_CONFIG", "regional-us-central1")

# ---------------------------------------------------------------------------
# Document AI configuration
# ---------------------------------------------------------------------------
DOCAI_LOCATION = os.getenv("DOCAI_LOCATION", "us")
DOCAI_PROCESSOR_ID = os.getenv("DOCAI_PROCESSOR_ID", "")

# ---------------------------------------------------------------------------
# Memory bank configuration
# ---------------------------------------------------------------------------
MEMORY_BANK_ENABLED = os.getenv("MEMORY_BANK_ENABLED", "false").lower() == "true"
MEMORY_BANK_ENDPOINT = os.getenv("MEMORY_BANK_ENDPOINT", "http://localhost:8080")
MEMORY_SPANNER_DIRECT = os.getenv("MEMORY_SPANNER_DIRECT", "false").lower() == "true"

# ---------------------------------------------------------------------------
# PageIndex configuration
# ---------------------------------------------------------------------------
PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
PAGEINDEX_ENABLED = os.getenv("PAGEINDEX_ENABLED", "").lower() == "true" if os.getenv("PAGEINDEX_ENABLED") else bool(PAGEINDEX_API_KEY)

# ---------------------------------------------------------------------------
# TurboTax Cludo search configuration (optional)
# ---------------------------------------------------------------------------
CLUDO_CUSTOMER_ID = os.getenv("CLUDO_CUSTOMER_ID", "")
CLUDO_ENGINE_ID = os.getenv("CLUDO_ENGINE_ID", "")

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
LOG_FORMAT = os.getenv("LOG_FORMAT", "console")  # "console" for dev, "json" for production


def configure_logging():
    """Configure structlog. Call once at app startup."""
    import structlog

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()
