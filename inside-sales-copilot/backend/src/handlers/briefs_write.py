"""PUT /api/briefs/{id}, POST /api/briefs/{id}/confirm, /approve, /retry
(requirements R2.6 to R2.12, R7.1 to R7.5, R7.16, R9.10, R9.11).

None of these call Bedrock. Work that needs the model is queued for the worker.
"""
from __future__ import annotations

import copy
from typing import Any

from ..lib import constants as c
from ..lib import models
from ..lib.api import ApiDeps, ApiError, Caller, body, lambda_entry, path_id, respond
from ..services import invite_parser

READ_ONLY_SECTIONS = ("attendees", "caseStudies", "sources", "caseStudiesNote")
EDITABLE_SECTIONS = ("companySnapshot", "painPointHypotheses", "agenda", "discoveryQuestions")
MAX_ITEMS = 20


def _owned(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief = deps.store.get_owned(path_id(event, "id"), who.user_id)
    if brief is None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    return brief


def _send_or_fail(deps: ApiDeps, kind: str, brief_id: str, job_id: str) -> None:
    try:
        deps.queue.send(kind, brief_id, job_id)
    except Exception as exc:  # noqa: BLE001
        deps.log("queue_send_failed", {"briefId": brief_id, "errorType": type(exc).__name__})
        if kind == "extract_rules":
            deps.store.set_rules_result(brief_id, job_id, "failed", [])
        else:
            deps.store.fail(brief_id, job_id, "QUEUE_FAILED", None, "The brief could not be started. Please retry.")
        raise ApiError(503, "QUEUE_FAILED", "The request could not be queued. Please retry.") from None


# --- PUT /briefs/{id} -------------------------------------------------------------------------------------
def update_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief = _owned(event, who, deps)
    data = body(event)
    if brief["status"] == c.STATUS_AWAITING_CONFIRMATION and "parsedInvite" in data:
        parsed = _clean_parsed_invite(data["parsedInvite"])
        if not deps.store.save_parsed_invite(brief["briefId"], parsed):
            raise ApiError(409, "BRIEF_NOT_EDITABLE", "This brief can no longer be changed.")
    elif brief["status"] == c.STATUS_READY and "content" in data:
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ApiError(400, "INVALID_BODY", "Send the brief 'version' you edited.")
        content = validate_content_edit(data["content"], brief)
        if not deps.store.save_content(brief["briefId"], content, version):
            latest = deps.store.get(brief["briefId"]) or {}
            if latest.get("status") != c.STATUS_READY:
                raise ApiError(409, "BRIEF_NOT_EDITABLE", "This brief can no longer be edited.")
            raise ApiError(409, "CONFLICT", "The brief changed since you opened it. Reload and try again.")
    elif brief["status"] in (c.STATUS_AWAITING_CONFIRMATION, c.STATUS_READY):
        raise ApiError(400, "INVALID_BODY", "Nothing to save for this brief.")
    else:
        raise ApiError(409, "BRIEF_NOT_EDITABLE", "This brief cannot be edited now.")
    return respond(200, deps.store.view(deps.store.get(brief["briefId"])))


def _clean_parsed_invite(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(400, "INVALID_BODY", "The parsed invite is not valid.")
    candidate = {k: v for k, v in value.items() if k != "warnings"}
    try:
        models.validate("parsed_invite", candidate)
        cleaned, _ = invite_parser.normalize_invite(candidate)
    except (models.ModelValidationError, AttributeError, TypeError):
        raise ApiError(400, "INVALID_BODY", "The parsed invite is not valid.") from None
    cleaned["warnings"] = invite_parser.compute_warnings(cleaned)
    return cleaned


def validate_content_edit(content: Any, brief: dict[str, Any]) -> dict[str, Any]:
    """The SE may change text, add, or remove items in the editable sections. Facts must keep
    sources that the brief already cites, the agenda must still total 30 minutes, and the
    attendee, case study, and source lists cannot be changed (they come from code)."""
    def bad(message: str) -> ApiError:
        return ApiError(400, "INVALID_CONTENT", message)

    if not isinstance(content, dict):
        raise bad("The brief content is not valid.")
    try:
        models.validate("brief_content", content)
    except models.ModelValidationError:
        raise bad("The brief content is not valid.") from None
    current = brief.get("content") or {}
    for section in READ_ONLY_SECTIONS:
        if content.get(section) != current.get(section):
            raise bad(f"The '{section}' section cannot be edited.")
    for section in EDITABLE_SECTIONS:
        items = content[section]
        if len(items) > MAX_ITEMS:
            raise bad(f"The '{section}' section can have at most {MAX_ITEMS} items.")
        ids = [i["id"] for i in items]
        if len(set(ids)) != len(ids) or any(not 1 <= len(i) <= 40 for i in ids):
            raise bad(f"Items in '{section}' need unique ids.")
    allowed_urls = {s["url"] for s in current.get("sources", [])} | {s["url"] for s in (brief.get("draft") or {}).get("sources", [])}
    for section in ("companySnapshot", "painPointHypotheses"):
        for item in content[section]:
            if not set(item["sourceUrls"]) <= allowed_urls:
                raise bad("A source link was added that the brief does not cite. Sources cannot be invented.")
    fact_ids = {f["id"] for f in (brief.get("research") or {}).get("facts", [])}
    for item in content["painPointHypotheses"]:
        if not set(item["basedOnFactIds"]) <= fact_ids:
            raise bad("A pain point refers to a fact that does not exist.")
    total = sum(a["minutes"] for a in content["agenda"])
    if total != c.AGENDA_TOTAL_MINUTES:
        raise bad(f"The agenda adds up to {total} minutes. It must add up to {c.AGENDA_TOTAL_MINUTES}.")
    return copy.deepcopy(content)


# --- POST /briefs/{id}/confirm -------------------------------------------------------------------------------
def confirm_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief = _owned(event, who, deps)
    if brief["status"] != c.STATUS_AWAITING_CONFIRMATION:
        raise ApiError(409, "BRIEF_NOT_CONFIRMABLE", "This brief is not waiting for confirmation.")
    data = body(event)
    result = invite_parser.validate_confirmation(data.get("parsedInvite"), data.get("companyConfirmed") is True)
    if not result.ok:
        first = result.errors[0]
        raise ApiError(400, first["code"], first["message"], result.errors)
    invite = result.normalized
    job_id = deps.store.requeue(brief["briefId"], c.STATUS_AWAITING_CONFIRMATION,
                                {"parsedInvite": invite, "confirmedInvite": invite})
    if job_id is None:
        raise ApiError(409, "BRIEF_NOT_CONFIRMABLE", "This brief is not waiting for confirmation.")
    _send_or_fail(deps, "pipeline", brief["briefId"], job_id)
    deps.log("brief_confirmed", {"briefId": brief["briefId"]})
    return respond(202, {"briefId": brief["briefId"], "status": c.STATUS_QUEUED})


# --- POST /briefs/{id}/approve -------------------------------------------------------------------------------
def approve_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief = _owned(event, who, deps)
    if brief["status"] != c.STATUS_READY:
        raise ApiError(409, "BRIEF_NOT_APPROVABLE", "Only a ready brief can be approved.")
    job_id = deps.store.approve(brief["briefId"])
    if job_id is None:
        raise ApiError(409, "BRIEF_NOT_APPROVABLE", "Only a ready brief can be approved.")
    _send_or_fail(deps, "extract_rules", brief["briefId"], job_id)
    deps.log("brief_approved", {"briefId": brief["briefId"]})
    return respond(202, {"briefId": brief["briefId"], "status": c.STATUS_APPROVED, "rulesStatus": "pending"})


# --- POST /briefs/{id}/retry ----------------------------------------------------------------------------------
def retry_brief(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    brief = _owned(event, who, deps)
    if brief["status"] != c.STATUS_FAILED:
        raise ApiError(409, "BRIEF_NOT_FAILED", "Only a failed brief can be retried.")
    kind = "pipeline" if brief.get("confirmedInvite") else "parse"
    job_id = deps.store.requeue(brief["briefId"], c.STATUS_FAILED, clear_error=True)
    if job_id is None:
        raise ApiError(409, "BRIEF_NOT_FAILED", "Only a failed brief can be retried.")
    _send_or_fail(deps, kind, brief["briefId"], job_id)
    deps.log("brief_retried", {"briefId": brief["briefId"], "jobType": kind})
    return respond(202, {"briefId": brief["briefId"], "status": c.STATUS_QUEUED})


update_brief_handler = lambda_entry(update_brief)
confirm_brief_handler = lambda_entry(confirm_brief)
approve_brief_handler = lambda_entry(approve_brief)
retry_brief_handler = lambda_entry(retry_brief)
