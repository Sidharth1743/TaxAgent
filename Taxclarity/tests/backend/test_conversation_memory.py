from memory.spanner_graph import build_conversation_summary, format_conversation_context_prompt


def test_build_conversation_summary_mentions_user_and_advisor_context():
    summary = build_conversation_summary(
        [
            {"role": "user", "text": "I work at TCS and claimed 80C last year."},
            {"role": "agent", "text": "We discussed remaining 80C room and possible 80D savings."},
        ]
    )

    assert "Recent user questions" in summary
    assert "Recent advisor guidance" in summary
    assert "TCS" in summary


def test_format_conversation_context_prompt_includes_summary_topics_and_turns():
    prompt = format_conversation_context_prompt(
        {
            "loaded": True,
            "summary": "User discussed Form 16 and H-1B move.",
            "prior_topics": ["Form 16 upload", "H-1B move"],
            "recent_turns": [
                {"role": "user", "text": "Can you calculate my tax?", "created_at": "2026-03-09T00:00:00Z"},
                {"role": "agent", "text": "Yes, the new regime saves you money.", "created_at": "2026-03-09T00:00:01Z"},
            ],
        }
    )

    assert "Conversation summary" in prompt
    assert "Prior topics" in prompt
    assert "Recent turns" in prompt
    assert "Advisor:" in prompt


def test_format_conversation_context_prompt_filters_low_quality_advisor_turns():
    prompt = format_conversation_context_prompt(
        {
            "loaded": True,
            "summary": "User asked about hackathon prize tax.",
            "prior_topics": ["Hackathon prize tax"],
            "recent_turns": [
                {"role": "user", "text": "Do I need to pay tax on a 10 lakh cash prize?", "created_at": "2026-03-09T00:00:00Z"},
                {
                    "role": "agent",
                    "text": "**Clarifying Tax Inquiry** I'm focusing on the user question and my next step is to ask for details.",
                    "created_at": "2026-03-09T00:00:01Z",
                },
                {"role": "agent", "text": "Yes. Cash prizes are generally taxable under Indian tax rules.", "created_at": "2026-03-09T00:00:02Z"},
            ],
        }
    )

    assert "Clarifying Tax Inquiry" not in prompt
    assert "Cash prizes are generally taxable" in prompt
