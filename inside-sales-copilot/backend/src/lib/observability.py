"""Structured logging and metrics (requirements R10.13 to R10.16).

- Logs are JSON through AWS Lambda Powertools. Every line carries `briefId` and `requestId`
  (`-` until bound). A filter removes email addresses and sensitive fields before anything is
  written, so invite text and attendee emails never reach CloudWatch (R10.14).
- Metrics are CloudWatch EMF through Powertools. Only the names listed here may be used, so a
  typo cannot create a stray metric.
"""
from __future__ import annotations

import logging
import re
from typing import Any, IO

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

NAMESPACE = "InsideSalesCopilot"
SERVICE = "inside-sales-copilot"

# MVP metrics. ResearchLatencyMs and BriefFailed are added by task 3.2b.
METRIC_NAMES = frozenset({"BriefGenerated", "BedrockCalls", "BedrockThrottled"})

REDACTED = "[redacted]"
EMAIL_REPLACEMENT = "[email]"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*")
# Field names whose values must never be logged.
SENSITIVE_KEYS = frozenset({
    "invitetext", "invite_text", "invite", "inviteraw", "email", "emails", "attendee", "attendees",
    "token", "idtoken", "id_token", "accesstoken", "access_token", "refreshtoken", "authorization",
    "password", "secret", "notes", "body", "prompt", "reply", "usermessage", "user_message",
})


def scrub(value: Any, key: str | None = None) -> Any:
    """Return `value` with emails and tokens removed and sensitive fields replaced."""
    if key is not None and key.replace("-", "").replace("_", "").lower() in {k.replace("_", "") for k in SENSITIVE_KEYS}:
        return REDACTED
    if isinstance(value, str):
        value = _JWT_RE.sub(REDACTED, _BEARER_RE.sub("Bearer " + REDACTED, value))
        return _EMAIL_RE.sub(EMAIL_REPLACEMENT, value)
    if isinstance(value, dict):
        return {k: scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [scrub(v) for v in value]
    return value


_STANDARD_ATTRS = frozenset(logging.LogRecord("x", 0, "x", 0, "x", None, None).__dict__) | {"message", "asctime", "taskName"}


def _scrub_exception(exc: BaseException, _seen: set[int] | None = None) -> None:
    """Remove emails and tokens from an exception's message (and its causes) before it is logged."""
    seen = _seen if _seen is not None else set()
    if id(exc) in seen:
        return
    seen.add(id(exc))
    try:
        exc.args = tuple(scrub(a) if isinstance(a, (str, dict, list, tuple)) else a for a in exc.args)
    except (AttributeError, TypeError):
        pass
    for linked in (exc.__cause__, exc.__context__):
        if linked is not None:
            _scrub_exception(linked, seen)


class RedactingFilter(logging.Filter):
    """Cleans every record before it is formatted: message, arguments, extra fields, exceptions."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.msg) if isinstance(record.msg, str) else scrub(str(record.msg))
        if record.args:
            record.args = tuple(scrub(a) for a in record.args) if isinstance(record.args, tuple) else scrub(record.args)
        for key in list(record.__dict__):
            if key not in _STANDARD_ATTRS:
                record.__dict__[key] = scrub(record.__dict__[key], key)
        if record.exc_info and record.exc_info[1] is not None:
            _scrub_exception(record.exc_info[1])  # the class name and traceback stay, the values do not
        if record.exc_text:
            record.exc_text = scrub(record.exc_text)
        return True


def get_logger(service: str = SERVICE, stream: IO[str] | None = None, level: str = "INFO") -> Logger:
    """A Powertools logger that redacts, with briefId and requestId on every line."""
    logger = Logger(service=service, level=level, stream=stream) if stream else Logger(service=service, level=level)
    handler = logger.registered_handler
    if not any(isinstance(f, RedactingFilter) for f in handler.filters):
        handler.addFilter(RedactingFilter())
    logger.append_keys(briefId="-", requestId="-")
    return logger


def bind_brief(logger: Logger, brief_id: str) -> None:
    logger.append_keys(briefId=brief_id)


def bind_request(logger: Logger, request_id: str) -> None:
    logger.append_keys(requestId=request_id)


class PowertoolsMetrics:
    """Counts Bedrock calls and briefs as CloudWatch metrics. Implements the client's MetricsSink."""

    def __init__(self, metrics: Metrics | None = None):
        self._metrics = metrics or Metrics(namespace=NAMESPACE, service=SERVICE)

    def incr(self, name: str, count: int = 1) -> None:
        if name not in METRIC_NAMES:
            raise ValueError(f"unknown metric name: {name!r}")
        self._metrics.add_metric(name=name, unit=MetricUnit.Count, value=count)

    def flush(self) -> None:
        """Write the collected metrics. Call once at the end of each Lambda invocation."""
        if self._metrics.metric_set:
            self._metrics.flush_metrics()
