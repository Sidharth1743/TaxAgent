"""
ADK Web entrypoint for the 'adk' app name.
Exposes root_agent for `adk web agents` when app_name is 'adk'.
"""

from adk.root_agent.agent import root_agent  # noqa: F401
