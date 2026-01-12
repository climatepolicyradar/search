"""Centralized logging configuration with Rich formatting."""

import logging

from rich.logging import RichHandler


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get a configured logger with RichHandler.

    :param name: Logger name (typically __name__)
    :param level: Logging level (default: INFO)
    :return: Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if logger is already configured
    if not logger.handlers:
        logger.addHandler(RichHandler())

    return logger
