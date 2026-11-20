"""POST /api/briefs/{id}/rules, GET /api/rules, DELETE /api/rules/{ruleId}, GET /api/case-studies
(requirements R5.2, R5.3, R5.10, R5.11, R7.10 to R7.15)."""
from __future__ import annotations

from typing import Any

from ..lib import constants as c
from ..lib.api import (RULE_ID_RE, ApiDeps, ApiError, Caller, body, lambda_entry, path_id, require_bu, respond)
from ..services import rules as rules_mod


def decide_rules(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    """Keep or discard each proposed rule."""
    brief = deps.store.get_owned(path_id(event, "id"), who.user_id)
    if brief is None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    proposals = brief.get("ruleProposals") or []
    if brief.get("rulesStatus") != "ready" or not proposals:
        raise ApiError(409, "NO_PROPOSALS", "There are no rule proposals to review.")
    decisions = body(event).get("decisions")
    valid = (isinstance(decisions, list) and 1 <= len(decisions) <= c.MAX_RULE_PROPOSALS
             and all(isinstance(d, dict) and isinstance(d.get("proposalId"), str) and isinstance(d.get("keep"), bool)
                     for d in decisions))
    if not valid:
        raise ApiError(400, "INVALID_BODY", "Send 'decisions' as a list of {proposalId, keep}.")
    # Claim the proposals first, so two requests at once cannot save them twice.
    if not deps.store.set_rule_proposals_handled(brief["briefId"]):
        raise ApiError(409, "NO_PROPOSALS", "There are no rule proposals to review.")
    saved = rules_mod.apply_decisions(deps.rules, who.user_id, proposals, decisions, brief["briefId"])
    deps.log("rules_decided", {"briefId": brief["briefId"], "kept": len(saved)})
    return respond(200, {"saved": [r["ruleId"] for r in saved]})


def list_rules(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    items = [{"ruleId": r["ruleId"], "text": r["text"], "createdAt": r["createdAt"]} for r in deps.rules.list_all(who.user_id)]
    return respond(200, {"items": items})


def delete_rule(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    rule_id = path_id(event, "ruleId", RULE_ID_RE)
    if not deps.rules.delete(who.user_id, rule_id):
        raise ApiError(404, "NOT_FOUND", "Not found.")
    return respond(204)


def list_case_studies(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    """Only the caller's own BU, from the token. A `bu` query parameter is ignored (R5.2)."""
    bu = require_bu(who)
    items = [{"id": s.id, "title": s.title, "summary": s.summary, "client_industry": s.client_industry,
              "tags": list(s.tags), "url": s.url} for s in deps.studies if s.bu == bu]
    return respond(200, {"bu": bu, "items": items})


ROUTES = {
    "POST /api/briefs/{id}/rules": decide_rules,
    "GET /api/rules": list_rules,
    "DELETE /api/rules/{ruleId}": delete_rule,
}


def rules_router(event: dict[str, Any], who: Caller, deps: ApiDeps) -> dict[str, Any]:
    route = ROUTES.get(event.get("routeKey", ""))
    if route is None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    return route(event, who, deps)


rules_handler = lambda_entry(rules_router)
case_studies_handler = lambda_entry(list_case_studies)
