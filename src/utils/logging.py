"""Log configuration.

Prefers a pretty, column-aligned console renderer for humans by default.
Set LOG_FORMAT=json to switch to JSON-per-line (for container log
aggregators, CI log parsers, etc.).
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def _configure_uvicorn_filters() -> None:
    """Silence noisy high-frequency poll endpoints from uvicorn's access log.

    The frontend polls /brokers + /auth/*/status + /health frequently. Those
    every-few-seconds 200s drown out the interesting lines (POSTs, errors).
    Keep the log useful by dropping them.
    """

    class _DropNoisyPaths(logging.Filter):
        _NOISY = (
            "/brokers",
            "/events",
            "/health",
            "/auth/",
        )

        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()

            if "POST" in msg:
                return True
            return not any(p in msg for p in self._NOISY)

    logging.getLogger("uvicorn.access").addFilter(_DropNoisyPaths())

def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "console").lower()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    _configure_uvicorn_filters()

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:

        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=sys.stdout.isatty(),

                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
