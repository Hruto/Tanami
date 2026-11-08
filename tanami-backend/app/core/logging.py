"""Structured logging.

JSON in every environment except local development, always carrying the request
id from ``app.core.context``. Personal data, tokens and image bytes never reach a
log line (TQA 12).
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.core.context import get_request_id, get_user_id


def _add_request_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Attach the request id (and pseudonymous user id) to every record (TQA 12).

    The ids live in plain ``ContextVar``s owned by ``app.core.context``, which
    ``merge_contextvars`` does not read, so they are added explicitly.
    """
    request_id = get_request_id()
    if request_id:
        event_dict.setdefault("request_id", request_id)
    user_id = get_user_id()
    if user_id:
        event_dict.setdefault("user_id", user_id)
    return event_dict


def configure_logging(level: str, *, json_output: bool) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_request_context,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=numeric_level, format="%(message)s", stream=sys.stdout, force=True)
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
