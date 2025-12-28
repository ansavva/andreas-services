"""
Central logging configuration for the backend.
Sets up JSON-formatted logs suitable for CloudWatch Logs Insights.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_configured = False


class JsonFormatter(logging.Formatter):
    """Render log records as structured JSON for easier querying."""

    def format(self, record: logging.LogRecord) -> str:
        log: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Optional context fields provided via logger.extra
        if hasattr(record, "aws_request_id") and record.aws_request_id:
            log["aws_request_id"] = record.aws_request_id
        if hasattr(record, "path") and record.path:
            log["path"] = record.path
        if hasattr(record, "method") and record.method:
            log["method"] = record.method
        if hasattr(record, "user_id") and record.user_id:
            log["user_id"] = record.user_id

        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log)


def configure_logging(level: Optional[str] = None) -> None:
    """Configure root logger once with JSON formatter (idempotent)."""
    global _configured
    if _configured:
        return

    desired_level = level or os.getenv("LOG_LEVEL", "INFO")
    root_logger = logging.getLogger()
    root_logger.setLevel(desired_level.upper())

    # Remove pre-existing handlers (Lambda adds one by default)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)

    _configured = True
