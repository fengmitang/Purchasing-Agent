"""ASGI entry point."""

from app.bootstrap import create_application

app = create_application()
