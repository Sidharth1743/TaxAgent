import json
from pathlib import Path


def test_india_taxtmi_agent_card_valid():
    root = Path(__file__).parent.parent.parent
    card_path = root / "agents/adk/taxtmi_a2a/.well-known/agent.json"
    with open(card_path) as f:
        card = json.load(f)

    assert card["jurisdiction"] == "india"
    assert "capabilities" in card
    assert "income_tax" in card["capabilities"]


def test_caclub_agent_card_valid():
    """CAClubIndia is an India-jurisdiction agent (port 8001)."""
    root = Path(__file__).parent.parent.parent
    card_path = root / "agents/adk/caclub_a2a/.well-known/agent.json"
    with open(card_path) as f:
        card = json.load(f)

    assert card["jurisdiction"] == "india", (
        f"CAClubIndia agent should be jurisdiction 'india', got '{card['jurisdiction']}'"
    )
    assert "capabilities" in card
    assert "income_tax" in card["capabilities"]
