"""Builds API Gateway HTTP API (v2) events with JWT authorizer claims, for handler tests."""
from __future__ import annotations

import json
from typing import Any

from backend.src.lib.api import ApiDeps, JobQueue
from backend.tests.env_helpers import Env


def event(route: str, *, user: str | None = "alice", bu: str | None = "ServiceNow", body: Any = None,
          path: dict[str, str] | None = None, query: dict[str, str] | None = None, raw_body: str | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "routeKey": route,
        "pathParameters": path or {},
        "queryStringParameters": query,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "req-1"},
    }
    if user is not None:
        claims = {"sub": user}
        if bu is not None:
            claims["custom:bu"] = bu
        ev["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    if raw_body is not None:
        ev["body"] = raw_body
    elif body is not None:
        ev["body"] = json.dumps(body)
    return ev


def api_deps(env: Env) -> ApiDeps:
    return ApiDeps(store=env.store, queue=JobQueue(env.sqs, env.queue_url), rules=env.deps.rules,
                   studies=env.deps.studies, log=lambda e, d: env.events.append((e, d)))


def payload(resp: dict[str, Any]) -> Any:
    return json.loads(resp["body"]) if resp.get("body") else None
