"""Application configuration loaded from environment variables."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from utils.exceptions import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Validated settings shared by the application."""

    app_name: str
    log_level: int
    supported_drawing_extensions: tuple[str, ...]


def load_settings() -> Settings:
    """Load settings and fail clearly when configuration is invalid."""
    app_name = os.getenv("APP_NAME", "Automated Quantity Takeoff")
    requested_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = logging.getLevelName(requested_log_level)

    if not isinstance(log_level, int):
        raise ConfigurationError(
            f"Invalid LOG_LEVEL {requested_log_level!r}. "
            "Choose DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )

    return Settings(
        app_name=app_name,
        log_level=log_level,
        supported_drawing_extensions=("pdf", "png", "jpg", "jpeg"),
    )
