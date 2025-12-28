"""
Configure structlog for JSON logging compatible with CloudWatch.
"""
import logging
import sys
from typing import Optional

import structlog
from structlog.stdlib import ProcessorFormatter
from src.config.config import Config

_configured = False


def configure_logging(level: Optional[str] = None) -> None:
    """Configure structlog once with JSON output."""
    global _configured
    if _configured:
        return

    log_level_name = (level or Config.LOG_LEVEL).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    handler = logging.StreamHandler()
    handler.setFormatter(
        ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                timestamper,
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _configured = True
