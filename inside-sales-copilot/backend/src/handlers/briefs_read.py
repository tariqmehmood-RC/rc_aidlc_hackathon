"""POST /api/briefs, GET /api/briefs, GET /api/briefs/{id} (requirements R2.1 to R2.3, R8, R9)."""
from __future__ import annotations

from typing import Any

from ..lib import constants as c
from ..lib.api import ApiDeps, ApiError, Caller, body, lambda_entry, path_id, query, require_bu, respond
from ..lib.brief_store import InvalidCursor


def create_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    bu = require_bu(who)
    data = body(event)
    text = data.get("inviteText")
    if not isinstance(text, str):
        raise ApiError(400, "INVALID_BODY", "Send the invite text as 'inviteText'.")
    if len(text) > c.MAX_INVITE_CHARS:
        raise ApiError(400, "INVITE_TOO_LONG", f"The invite is longer than {c.MAX_INVITE_CHARS:,} characters.")
    if not text.strip():
        raise ApiError(400, "INVITE_EMPTY", "Paste the meeting invite first.")
    brief, job_id = deps.store.create(who.user_id, bu, text)
    try:
        deps.queue.send("parse", brief["briefId"], job_id)
    except Exception as exc:  # noqa: BLE001
        # Do not leave a brief waiting forever for a message that was never sent.
        deps.store.fail(brief["briefId"], job_id, "QUEUE_FAILED", None, "The brief could not be started. Please retry.")
        deps.log("queue_send_failed", {"briefId": brief["briefId"], "errorType": type(exc).__name__})
        raise ApiError(503, "QUEUE_FAILED", "The brief could not be started. Please retry.") from None
    deps.log("brief_created", {"briefId": brief["briefId"]})
    return respond(202, {"briefId": brief["briefId"], "status": c.STATUS_QUEUED})


def get_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief_id = path_id(event, "id")
    brief = deps.store.get_owned(brief_id, who.user_id)
    if brief is None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    brief = deps.store.expire_if_stuck(brief)
    return respond(200, deps.store.view(brief, deps.store.queue_position(brief)))


def list_briefs(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    q = query(event)
    limit_text = q.get("limit", str(c.PAGE_SIZE))
    if not limit_text.isdigit() or not 1 <= int(limit_text) <= c.PAGE_SIZE:
        raise ApiError(400, "INVALID_LIMIT", f"limit must be between 1 and {c.PAGE_SIZE}.")
    try:
        items, cursor = deps.store.list_for_user(who.user_id, int(limit_text), q.get("cursor") or None)
    except InvalidCursor:
        raise ApiError(400, "INVALID_CURSOR", "The page cursor is not valid.") from None
    return respond(200, {"items": items, "nextCursor": cursor})


create_brief_handler = lambda_entry(create_brief)
get_brief_handler = lambda_entry(get_brief)
list_briefs_handler = lambda_entry(list_briefs)
