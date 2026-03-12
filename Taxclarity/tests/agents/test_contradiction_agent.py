"""Tests for contradiction detection module."""

import pytest

from agents.contradiction_agent import detect_contradictions


class TestDetectContradictions:
    """Test detect_contradictions with various source configurations."""

    def test_disagreeing_sources_different_amounts(self):
        """Sources disagree on a numeric limit -- should flag contradiction."""
        claims = [
            {
                "claim": "Section 80C deduction limit is 1.5 lakh",
                "citations": ["https://caclub.example.com/80c"],
                "source": "caclub",
            },
            {
                "claim": "Section 80C deduction limit is 2 lakh",
                "citations": ["https://taxtmi.example.com/80c"],
                "source": "taxtmi",
            },
        ]
        result = detect_contradictions(claims)
        assert len(result) >= 1
        contradiction = result[0]
        assert "topic" in contradiction
        assert "positions" in contradiction
        assert len(contradiction["positions"]) == 2
        assert "analysis" in contradiction
        # Verify positions have correct structure
        for pos in contradiction["positions"]:
            assert "source" in pos
            assert "claim" in pos
            assert "citations" in pos

    def test_agreeing_sources_returns_empty(self):
        """Sources that agree on the same topic should produce no contradictions."""
        claims = [
            {
                "claim": "Section 80C deduction limit is 1.5 lakh",
                "citations": ["https://caclub.example.com/80c"],
                "source": "caclub",
            },
            {
                "claim": "The 80C limit is 1.5 lakh per year",
                "citations": ["https://taxtmi.example.com/80c"],
                "source": "taxtmi",
            },
        ]
        result = detect_contradictions(claims)
        assert result == []

    def test_single_source_no_contradiction(self):
        """Single source cannot contradict itself."""
        claims = [
            {
                "claim": "80C limit is 1.5 lakh",
                "citations": ["https://caclub.example.com/80c"],
                "source": "caclub",
            },
        ]
        result = detect_contradictions(claims)
        assert result == []

    def test_empty_input(self):
        """Empty claims list returns empty contradictions."""
        result = detect_contradictions([])
        assert result == []

    def test_eligibility_contradiction(self):
        """Detect yes/no disagreement on eligibility."""
        claims = [
            {
                "claim": "NRIs are eligible for section 80C deductions",
                "citations": ["https://caclub.example.com/nri"],
                "source": "caclub",
            },
            {
                "claim": "NRIs are not eligible for 80C deductions",
                "citations": ["https://taxtmi.example.com/nri"],
                "source": "taxtmi",
            },
        ]
        result = detect_contradictions(claims)
        assert len(result) >= 1
