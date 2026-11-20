"""Shared code for the API Lambdas (requirements R1.9, R10.20; design 6).

- The user id and BU come only from the JWT claims that API Gateway already verified. Any
  `userId` or `bu` in the body, query, or headers is ignored.
- Errors have one shape: {"error": {"code", "message"}}. No stack traces, ever.
- API Lambdas never call Bedrock. They read and write DynamoDB and send SQS messages.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from . import constants as c
from .brief_store import BriefStore
from .models import CaseStudy

REGION = "us-east-1"
MAX_BODY_BYTES = 12 * 1024
BRIEF_ID_RE = re.compile(r"^[0-9a-f]{32}$")
RULE_ID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
JSON_HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-store"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list[dict[str, str]] | None = None):
        super().__init__(code)
        self.status, self.code, self.message, self.details = status, code, message, details


@dataclass(frozen=True)
class Caller:
    user_id: str
    bu: str | None


def caller(event: dict[str, Any]) -> Caller:
    """The verified identity. 401 if the authorizer did not supply one."""
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        raise ApiError(401, "UNAUTHORIZED", "Sign in to continue.") from None
    sub = claims.get("sub") if isinstance(claims, dict) else None
    if not isinstance(sub, str) or not sub:
        raise ApiError(401, "UNAUTHORIZED", "Sign in to continue.")
    bu = claims.get("custom:bu")
    return Caller(sub, bu if isinstance(bu, str) and bu in c.BUSINESS_UNITS else None)


def require_bu(who: Caller) -> str:
    if who.bu is None:
        raise ApiError(403, "NO_BU", "Your account has no business unit. Ask an administrator to set one.")
    return who.bu


def body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if raw is None or raw == "":
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_BODY", "The request body is not valid.") from None
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ApiError(400, "BODY_TOO_LARGE", f"The request body is larger than {MAX_BODY_BYTES // 1024} KB.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise ApiError(400, "INVALID_BODY", "The request body must be JSON.") from None
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_BODY", "The request body must be a JSON object.")
    return data


def path_id(event: dict[str, Any], name: str, pattern: re.Pattern[str] = BRIEF_ID_RE) -> str:
    value = (event.get("pathParameters") or {}).get(name)
    if not isinstance(value, str) or not pattern.match(value):
        raise ApiError(404, "NOT_FOUND", "Not found.")  # a malformed id is simply not found
    return value


def query(event: dict[str, Any]) -> dict[str, str]:
    q = event.get("queryStringParameters") or {}
    return {k: v for k, v in q.items() if isinstance(v, str)}


def respond(status: int, payload: Any | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"statusCode": status, "headers": dict(JSON_HEADERS)}
    if payload is not None:
        out["body"] = json.dumps(payload, separators=(",", ":"))
    return out


def error_response(err: ApiError) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": err.code, "message": err.message}}
    if err.details:
        payload["error"]["details"] = err.details
    return respond(err.status, payload)


class JobQueue:
    """Sends job messages to the worker queue. The message holds ids only, never user data."""

    def __init__(self, client: Any, queue_url: str):
        self._client, self._url = client, queue_url

    def send(self, kind: str, brief_id: str, job_id: str) -> None:
        self._client.send_message(QueueUrl=self._url, MessageBody=json.dumps(
            {"type": kind, "briefId": brief_id, "jobId": job_id}))


@dataclass
class ApiDeps:
    store: BriefStore
    queue: JobQueue
    rules: Any
    studies: Sequence[CaseStudy]
    log: Callable[[str, dict[str, Any]], None] = field(default=lambda event, data: None)


_deps: ApiDeps | None = None


def default_deps() -> ApiDeps:
    """Built once per container from the environment variables CDK sets."""
    global _deps
    if _deps is None:
        import boto3

        from ..services.case_study_matcher import load_case_studies
        from ..services.rules import RulesStore
        from .observability import get_logger

        logger = get_logger(service="api")
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _deps = ApiDeps(
            store=BriefStore(ddb.Table(os.environ["BRIEFS_TABLE"])),
            queue=JobQueue(boto3.client("sqs", region_name=REGION), os.environ["JOBS_QUEUE_URL"]),
            rules=RulesStore(ddb.Table(os.environ["RULES_TABLE"])),
            studies=load_case_studies(),
            log=lambda event, data: logger.info(event, extra=data),
        )
    return _deps


Route = Callable[[dict[str, Any], Caller, ApiDeps], dict[str, Any]]


def run(route: Route, event: dict[str, Any], deps: ApiDeps | None = None) -> dict[str, Any]:
    """Call a route with the verified caller. Turns every error into a clean JSON response."""
    deps = deps or default_deps()
    try:
        return route(event, caller(event), deps)
    except ApiError as err:
        return error_response(err)
    except Exception as exc:  # noqa: BLE001 - nothing internal may leak to the client
        deps.log("unhandled_error", {"errorType": type(exc).__name__})
        return error_response(ApiError(500, "INTERNAL_ERROR", "Something went wrong. Please try again."))


def lambda_entry(route: Route) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        return run(route, event)

    handler.__name__ = getattr(route, "__name__", "handler")
    return handler
