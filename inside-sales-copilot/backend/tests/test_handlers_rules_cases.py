import copy

import pytest

from backend.src.handlers import briefs_write, rules_cases as h
from backend.src.lib import api
from backend.tests.api_helpers import api_deps, event, payload
from backend.tests.env_helpers import backend
from backend.tests.test_handlers_write import call, ready_brief, work


def brief_with_proposals(env):
    brief_id = ready_brief(env)
    content = copy.deepcopy(env.store.get(brief_id)["content"])
    content["discoveryQuestions"][0]["text"] = "What is your budget cycle?"
    call(briefs_write.update_brief, env, "PUT /api/briefs/{id}", brief_id, {"content": content, "version": 0})
    call(briefs_write.approve_brief, env, "POST /api/briefs/{id}/approve", brief_id)
    work(env)
    proposals = env.store.get(brief_id)["ruleProposals"]
    assert proposals
    return brief_id, proposals


def rules_call(env, route_key, *, path=None, body=None, user="alice"):
    return api.run(h.rules_router, event(route_key, user=user, path=path, body=body), api_deps(env))


def decide(env, brief_id, decisions, user="alice"):
    return rules_call(env, "POST /api/briefs/{id}/rules", path={"id": brief_id}, body={"decisions": decisions}, user=user)


# --- keep or discard -----------------------------------------------------------------------------------
def test_kept_proposals_are_saved_and_listed():
    with backend() as env:
        brief_id, proposals = brief_with_proposals(env)
        resp = decide(env, brief_id, [{"proposalId": proposals[0]["proposalId"], "keep": True}])
        assert resp["statusCode"] == 200 and len(payload(resp)["saved"]) == 1
        listed = payload(rules_call(env, "GET /api/rules"))["items"]
        assert [r["text"] for r in listed] == ["Always ask about the budget cycle."]
        brief = env.store.get(brief_id)
        assert brief["ruleProposals"] == [] and brief["rulesStatus"] == "none"


def test_discarded_proposals_are_not_saved():
    with backend() as env:
        brief_id, proposals = brief_with_proposals(env)
        decide(env, brief_id, [{"proposalId": proposals[0]["proposalId"], "keep": False}])
        assert payload(rules_call(env, "GET /api/rules"))["items"] == []


def test_deciding_twice_gives_409_and_saves_nothing_more():
    with backend() as env:
        brief_id, proposals = brief_with_proposals(env)
        keep = [{"proposalId": proposals[0]["proposalId"], "keep": True}]
        decide(env, brief_id, keep)
        resp = decide(env, brief_id, keep)
        assert resp["statusCode"] == 409 and payload(resp)["error"]["code"] == "NO_PROPOSALS"
        assert len(payload(rules_call(env, "GET /api/rules"))["items"]) == 1


def test_a_rule_already_saved_is_not_saved_twice():
    with backend() as env:
        env.deps.rules.add("alice", "always ask about the BUDGET cycle")
        brief_id = ready_brief(env)
        brief = env.store.get(brief_id)
        job = env.store.approve(brief_id)
        env.store.set_rules_result(brief_id, job, "ready", [{"proposalId": "p1", "text": "Always ask about the budget cycle.", "rationale": "r"}])
        resp = decide(env, brief_id, [{"proposalId": "p1", "keep": True}])
        assert payload(resp)["saved"] == [] and len(payload(rules_call(env, "GET /api/rules"))["items"]) == 1


@pytest.mark.parametrize("decisions", [None, [], "keep", [{"proposalId": 1, "keep": True}],
                                       [{"proposalId": "p", "keep": "yes"}], [{"proposalId": "p", "keep": True}] * 4])
def test_invalid_decisions_give_400(decisions):
    with backend() as env:
        brief_id, _ = brief_with_proposals(env)
        resp = decide(env, brief_id, decisions)
        assert resp["statusCode"] == 400 and env.store.get(brief_id)["rulesStatus"] == "ready"


def test_no_proposals_gives_409():
    with backend() as env:
        brief_id = ready_brief(env)
        assert decide(env, brief_id, [{"proposalId": "p", "keep": True}])["statusCode"] == 409


def test_another_users_brief_gives_404():
    with backend() as env:
        brief_id, proposals = brief_with_proposals(env)
        resp = decide(env, brief_id, [{"proposalId": proposals[0]["proposalId"], "keep": True}], user="bob")
        assert resp["statusCode"] == 404
        assert env.store.get(brief_id)["rulesStatus"] == "ready"


# --- list and delete -------------------------------------------------------------------------------------------
def test_list_and_delete_are_scoped_to_the_caller():
    with backend() as env:
        mine = env.deps.rules.add("alice", "Ask about budget.")
        theirs = env.deps.rules.add("bob", "Ask about timeline.")
        assert [r["text"] for r in payload(rules_call(env, "GET /api/rules"))["items"]] == ["Ask about budget."]
        resp = rules_call(env, "DELETE /api/rules/{ruleId}", path={"ruleId": theirs["ruleId"]})
        assert resp["statusCode"] == 404
        assert len(env.deps.rules.list_all("bob")) == 1
        resp = rules_call(env, "DELETE /api/rules/{ruleId}", path={"ruleId": mine["ruleId"]})
        assert resp["statusCode"] == 204 and env.deps.rules.list_all("alice") == []


def test_a_malformed_rule_id_is_not_found():
    with backend() as env:
        assert rules_call(env, "DELETE /api/rules/{ruleId}", path={"ruleId": "../x"})["statusCode"] == 404


def test_an_unknown_route_is_not_found():
    with backend() as env:
        assert rules_call(env, "PATCH /api/rules")["statusCode"] == 404


# --- case studies ------------------------------------------------------------------------------------------------
def cases(env, **kw):
    return api.run(h.list_case_studies, event("GET /api/case-studies", **kw), api_deps(env))


def test_case_studies_are_only_from_the_callers_bu_and_the_query_is_ignored():
    with backend() as env:
        out = payload(cases(env, bu="AWS", query={"bu": "ServiceNow"}))
        assert out["bu"] == "AWS" and len(out["items"]) == 9
        by_id = {s.id: s for s in env.deps.studies}
        assert all(by_id[i["id"]].bu == "AWS" for i in out["items"])
        assert set(out["items"][0]) == {"id", "title", "summary", "client_industry", "tags", "url"}


def test_two_users_with_different_bus_get_different_lists():
    with backend() as env:
        aws = {i["id"] for i in payload(cases(env, bu="AWS"))["items"]}
        snow = {i["id"] for i in payload(cases(env, bu="ServiceNow"))["items"]}
        assert aws and snow and aws.isdisjoint(snow) and len(snow) == 13


@pytest.mark.parametrize("bu", [None, "Oracle"])
def test_a_user_with_no_valid_bu_gets_403(bu):
    with backend() as env:
        resp = cases(env, bu=bu)
        assert resp["statusCode"] == 403 and payload(resp)["error"]["code"] == "NO_BU"


def test_unauthenticated_gets_401():
    with backend() as env:
        assert cases(env, user=None)["statusCode"] == 401
