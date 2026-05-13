"""
BKAi Structured Logger.

Provides JSON-formatted structured logging for observability,
debugging, and agent pipeline tracing.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured logging for the entire application.

    Uses structlog with JSON rendering for production and
    colored console output for development.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    # Determine if running in a terminal (dev) or piped (prod)
    is_dev = sys.stderr.isatty()

    # Configure structlog processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        # Pretty console output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON output for production (structured logging)
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "chromadb", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a named structured logger.

    Args:
        name: Logger name (typically __name__ of the calling module).

    Returns:
        A bound structlog logger instance.
    """
    return structlog.get_logger(name)


class AgentTracer:
    """
    Utility for tracing agent pipeline execution.

    Logs structured events for each step of the multi-agent workflow,
    enabling performance monitoring and debugging.

    Usage:
        tracer = AgentTracer("orchestrator")
        tracer.start("query_rewrite", query="user question")
        # ... do work ...
        tracer.end("query_rewrite", result="rewritten query")
    """

    def __init__(self, agent_name: str) -> None:
        self.logger = get_logger(f"agent.{agent_name}")
        self.agent_name = agent_name

    def start(self, step: str, **kwargs: Any) -> None:
        """Log the start of an agent step."""
        self.logger.info(
            "agent_step_start",
            agent=self.agent_name,
            step=step,
            **kwargs,
        )

    def end(self, step: str, **kwargs: Any) -> None:
        """Log the end of an agent step."""
        self.logger.info(
            "agent_step_end",
            agent=self.agent_name,
            step=step,
            **kwargs,
        )

    def error(self, step: str, error: str, **kwargs: Any) -> None:
        """Log an error during an agent step."""
        self.logger.error(
            "agent_step_error",
            agent=self.agent_name,
            step=step,
            error=error,
            **kwargs,
        )

    def metric(self, name: str, value: float, **kwargs: Any) -> None:
        """Log a performance metric."""
        self.logger.info(
            "agent_metric",
            agent=self.agent_name,
            metric_name=name,
            metric_value=value,
            **kwargs,
        )
