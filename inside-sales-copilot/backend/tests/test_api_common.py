import base64
import json

import pytest

from backend.src.lib import api
from backend.tests.api_helpers import event, payload


class Deps:
    def __init__(self):
        self.logged = []

    def log(self, e, d):
        self.logged.append((e, d))


def echo(ev, who, deps):
    return api.respond(200, {"user": who.user_id, "bu": who.bu, "body": api.body(ev)})


def test_identity_comes_only_from_the_verified_claims():
    ev = event("POST /api/x", user="alice", bu="AWS",
               body={"userId": "mallory", "bu": "ServiceNow"}, query={"bu": "Salesforce", "userId": "mallory"})
    ev["headers"] = {"x-user-id": "mallory", "x-bu": "Salesforce"}
    out = payload(api.run(echo, ev, Deps()))
    assert (out["user"], out["bu"]) == ("alice", "AWS")


@pytest.mark.parametrize("ev", [
    event("GET /api/x", user=None),
    {"requestContext": {"authorizer": {"jwt": {"claims": {}}}}},
    {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": ""}}}}},
    {},
])
def test_missing_claims_give_401(ev):
    resp = api.run(echo, ev, Deps())
    assert resp["statusCode"] == 401 and payload(resp)["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("bu", [None, "Oracle", "all", "aws"])
def test_an_unknown_bu_claim_counts_as_no_bu(bu):
    who = api.caller(event("GET /x", bu=bu))
    assert who.bu is None
    with pytest.raises(api.ApiError) as err:
        api.require_bu(who)
    assert err.value.status == 403 and err.value.code == "NO_BU"


def test_oversized_body_gives_400():
    resp = api.run(echo, event("POST /x", raw_body=json.dumps({"a": "x" * 13000})), Deps())
    assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == "BODY_TOO_LARGE"


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"text"', "{bad"])
def test_bodies_that_are_not_json_objects_give_400(raw):
    resp = api.run(echo, event("POST /x", raw_body=raw), Deps())
    assert resp["statusCode"] == 400 and payload(resp)["error"]["code"] == "INVALID_BODY"


def test_base64_bodies_are_decoded():
    ev = event("POST /x", raw_body=base64.b64encode(b'{"a": 1}').decode())
    ev["isBase64Encoded"] = True
    assert payload(api.run(echo, ev, Deps()))["body"] == {"a": 1}


def test_an_unexpected_exception_returns_a_generic_500_without_a_traceback():
    def broken(ev, who, deps):
        raise KeyError("secret-table-name jane@delta.com")

    deps = Deps()
    resp = api.run(broken, event("GET /x"), deps)
    assert resp["statusCode"] == 500
    text = resp["body"]
    assert "Traceback" not in text and "secret-table-name" not in text and "jane@" not in text and "KeyError" not in text
    assert payload(resp) == {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again."}}
    assert deps.logged == [("unhandled_error", {"errorType": "KeyError"})]


def test_api_errors_keep_their_status_code_and_details():
    def conflict(ev, who, deps):
        raise api.ApiError(409, "CONFLICT", "Changed.", [{"code": "A", "message": "b"}])

    resp = api.run(conflict, event("GET /x"), Deps())
    assert resp["statusCode"] == 409 and payload(resp)["error"]["details"] == [{"code": "A", "message": "b"}]


@pytest.mark.parametrize("value", ["../etc", "ABC", "0" * 31, "g" * 32, None, "' OR 1=1"])
def test_malformed_path_ids_are_not_found(value):
    with pytest.raises(api.ApiError) as err:
        api.path_id({"pathParameters": {"id": value}}, "id")
    assert err.value.status == 404


def test_valid_ids_pass():
    assert api.path_id({"pathParameters": {"id": "a" * 32}}, "id") == "a" * 32
    assert api.path_id({"pathParameters": {"r": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}}, "r", api.RULE_ID_RE)


def test_responses_are_json_and_not_cached():
    resp = api.respond(200, {"a": 1})
    assert resp["headers"] == {"Content-Type": "application/json", "Cache-Control": "no-store"}
    assert api.respond(204)["statusCode"] == 204 and "body" not in api.respond(204)


def test_the_job_queue_sends_ids_only():
    sent = []

    class Client:
        def send_message(self, **kw):
            sent.append(kw)

    api.JobQueue(Client(), "https://queue").send("parse", "b" * 32, "j")
    assert sent == [{"QueueUrl": "https://queue", "MessageBody": json.dumps({"type": "parse", "briefId": "b" * 32, "jobId": "j"})}]


def test_api_lambdas_never_import_bedrock():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    for path in [src / "lib" / "api.py", *sorted((src / "handlers").glob("*.py"))]:
        if path.name == "worker.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "bedrock" not in text.lower(), path.name
