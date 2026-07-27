"""
Structured JSON logger — CloudWatch-friendly output.
All ETL stages use get_logger(__name__) to get a named logger.
Emits JSON with: timestamp, level, logger, message, stage, plus any extra fields.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional


class StructuredFormatter(logging.Formatter):
    """Format log records as single-line JSON objects for CloudWatch ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach stage and any extra fields set on the record
        for attr in ("stage", "event", "file", "records", "duration_seconds", "error"):
            value = getattr(record, attr, None)
            if value is not None:
                log_entry[attr] = value

        # Attach exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Return a logger that writes structured JSON to stdout.
    Call once per module: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    if level:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    return logger


def configure_root_logger(level: str = "INFO") -> None:
    """Configure the root logger once at application startup."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers (avoids duplicate output)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
