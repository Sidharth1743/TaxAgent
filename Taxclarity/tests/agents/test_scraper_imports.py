"""Tests verifying all A2A agents use direct imports (no subprocess) and correct DATA_DIR."""

import os


def _read_agent_source(agent_subdir: str) -> str:
    """Read the source code of an A2A agent file."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "agents", "adk", agent_subdir, "agent.py"
    )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --- No subprocess tests ---


def test_no_subprocess_in_caclub():
    src = _read_agent_source("caclub_a2a")
    assert "subprocess" not in src, "caclub_a2a still uses subprocess"


def test_no_subprocess_in_taxtmi():
    src = _read_agent_source("taxtmi_a2a")
    assert "subprocess" not in src, "taxtmi_a2a still uses subprocess"


def test_no_subprocess_in_turbotax():
    src = _read_agent_source("turbotax_a2a")
    assert "subprocess" not in src, "turbotax_a2a still uses subprocess"


def test_no_subprocess_in_taxprofblog():
    src = _read_agent_source("taxprofblog_a2a")
    assert "subprocess" not in src, "taxprofblog_a2a still uses subprocess"


# --- DATA_DIR tests ---


def test_caclub_data_dir():
    from agents.adk.caclub_a2a.agent import DATA_DIR

    assert DATA_DIR.endswith("data"), f"caclub DATA_DIR should end with 'data', got: {DATA_DIR}"


def test_taxtmi_data_dir():
    from agents.adk.taxtmi_a2a.agent import DATA_DIR

    assert DATA_DIR.endswith("data"), f"taxtmi DATA_DIR should end with 'data', got: {DATA_DIR}"


def test_turbotax_data_dir():
    from agents.adk.turbotax_a2a.agent import DATA_DIR

    assert DATA_DIR.endswith("data"), f"turbotax DATA_DIR should end with 'data', got: {DATA_DIR}"


def test_taxprofblog_data_dir():
    from agents.adk.taxprofblog_a2a.agent import DATA_DIR

    assert DATA_DIR.endswith("data"), f"taxprofblog DATA_DIR should end with 'data', got: {DATA_DIR}"


# --- Direct import tests ---


def test_caclub_imports_run_directly():
    src = _read_agent_source("caclub_a2a")
    assert "from agents.caclub_agent import run" in src, (
        "caclub_a2a should import run directly from agents.caclub_agent"
    )


def test_taxtmi_imports_run_directly():
    src = _read_agent_source("taxtmi_a2a")
    assert "from agents.taxtmi_agent import run" in src, (
        "taxtmi_a2a should import run directly from agents.taxtmi_agent"
    )


def test_turbotax_imports_run_directly():
    src = _read_agent_source("turbotax_a2a")
    assert "from agents.turbotax_agent import run" in src, (
        "turbotax_a2a should import run directly from agents.turbotax_agent"
    )


def test_taxprofblog_imports_run_directly():
    src = _read_agent_source("taxprofblog_a2a")
    assert "from agents.taxprofblog_agent import run" in src, (
        "taxprofblog_a2a should import run directly from agents.taxprofblog_agent"
    )
