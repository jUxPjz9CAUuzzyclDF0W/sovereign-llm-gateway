"""ASGI entrypoint: `uvicorn sovgate.main:app`."""

from .app import create_app

app = create_app()
