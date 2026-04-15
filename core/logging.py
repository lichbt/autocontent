"""
Structured JSON logging for the SEO Content Engine.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import CONFIG


class JsonFormatter(logging.Formatter):
    """Formats logs as JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            payload["extra"] = record.extra_data

        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {record.levelname:<8} {record.name}: {record.getMessage()}"


class EngineLogger:
    """Small wrapper that accepts extra_data=... and maps it to stdlib logging extra."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def debug(self, msg: str, *args: Any, extra_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._logger.debug(msg, *args, extra={"extra_data": extra_data} if extra_data is not None else None, **kwargs)

    def info(self, msg: str, *args: Any, extra_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._logger.info(msg, *args, extra={"extra_data": extra_data} if extra_data is not None else None, **kwargs)

    def warning(self, msg: str, *args: Any, extra_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._logger.warning(msg, *args, extra={"extra_data": extra_data} if extra_data is not None else None, **kwargs)

    def error(self, msg: str, *args: Any, extra_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._logger.error(msg, *args, extra={"extra_data": extra_data} if extra_data is not None else None, **kwargs)

    def critical(self, msg: str, *args: Any, extra_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._logger.critical(msg, *args, extra={"extra_data": extra_data} if extra_data is not None else None, **kwargs)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._logger, item)


def setup_logger(name: str, log_file: Optional[str] = None) -> EngineLogger:
    """Set up a logger with JSON file output and console output."""

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, CONFIG.log_level, logging.INFO))

    if not logger.handlers:
        logger.propagate = False

        CONFIG.log_dir.mkdir(parents=True, exist_ok=True)
        resolved_log_file = log_file or f"{name.replace('.', '_')}.log"
        file_path = Path(CONFIG.log_dir) / resolved_log_file

        file_handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, CONFIG.log_level, logging.INFO))
        file_handler.setFormatter(JsonFormatter())

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, CONFIG.log_level, logging.INFO))
        console_handler.setFormatter(ConsoleFormatter())

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return EngineLogger(logger)


def get_logger(name: str) -> EngineLogger:
    """Return a configured logger instance."""
    return setup_logger(name)
