"""Logging configuration."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from .config import get_settings


def setup_logger(
    log_file: Optional[Path] = None,
    level: Optional[str] = None,
    rotation: str = "100 MB",
    retention: str = "30 days",
) -> None:
    """
    Configure logger with file and console outputs.

    Args:
        log_file: Path to log file (defaults to settings)
        level: Log level (defaults to settings)
        rotation: Log rotation size
        retention: Log retention period
    """
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Determine log level and file
    log_level = level or settings.log_level
    log_path = log_file or settings.log_file

    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Console handler with colors
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # File handler
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_level,
        rotation=rotation,
        retention=retention,
        compression="zip",
    )

    logger.info(f"Logger initialized - Level: {log_level}, File: {log_path}")


def get_logger(name: str):
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logger.bind(name=name)
