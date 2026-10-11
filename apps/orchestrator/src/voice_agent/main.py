"""ASGI import target for the local voice agent."""

from voice_agent.bootstrap import create_app

app = create_app()
