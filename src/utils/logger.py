"""
Logger Utility Module
Sets up logging configuration for the application.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Set up logging configuration.

    Args:
        config: Logging configuration dictionary

    Returns:
        Configured root logger
    """
    # Get configuration values
    level = config.get("level", "INFO").upper()
    log_file = config.get("file", "logs/facebook_poster.log")
    log_format = config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    date_format = config.get("date_format", "%Y-%m-%d %H:%M:%S")
    max_size_mb = config.get("max_size_mb", 10)
    backup_count = config.get("backup_count", 5)

    # Create log directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert level string to logging level
    log_level = getattr(logging, level, logging.INFO)

    # Create formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Log startup message
    logger.info(f"Logging initialized - Level: {level}, File: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for console output."""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_colored_logging(config: Dict[str, Any]) -> logging.Logger:
    """Set up logging with colored console output."""
    # Get configuration values
    level = config.get("level", "INFO").upper()
    log_file = config.get("file", "logs/facebook_poster.log")
    log_format = config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    date_format = config.get("date_format", "%Y-%m-%d %H:%M:%S")
    max_size_mb = config.get("max_size_mb", 10)
    backup_count = config.get("backup_count", 5)

    # Create log directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert level string to logging level
    log_level = getattr(logging, level, logging.INFO)

    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(log_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    logger.info(f"Logging initialized - Level: {level}, File: {log_file}")

    return logger