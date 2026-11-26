"""Logging setup shared by the application."""

import logging


def configure_logging(level: int) -> None:
    """Configure consistent console logging for local development."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
