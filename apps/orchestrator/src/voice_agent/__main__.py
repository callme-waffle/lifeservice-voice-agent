"""Local server entry point."""

import os

import uvicorn

from voice_agent.config import Settings


def main() -> None:
    settings = Settings.from_env(os.environ)
    uvicorn.run("voice_agent.main:app", host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    main()
