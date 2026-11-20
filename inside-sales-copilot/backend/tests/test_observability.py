import io
import json

import pytest
from aws_lambda_powertools import Metrics

from backend.src.lib import observability as obs
from backend.src.lib.bedrock_client import BedrockClient
from backend.src.lib.rate_limiter import TokenBucket
from backend.tests.fakes import FakeClock


def make_logger(name="test-service"):
    stream = io.StringIO()
    logger = obs.get_logger(service=name, stream=stream)
    return logger, stream


def lines(stream) -> list[dict]:
    return [json.loads(x) for x in stream.getvalue().splitlines() if x.strip()]


# --- logging --------------------------------------------------------------------------------------
def test_logs_are_json_lines_with_brief_id_and_request_id_even_before_binding():
    logger, stream = make_logger("svc-1")
    logger.info("hello")
    (line,) = lines(stream)
    assert line["message"] == "hello" and line["briefId"] == "-" and line["requestId"] == "-"


def test_bound_brief_id_and_request_id_appear_on_every_line():
    logger, stream = make_logger("svc-2")
    obs.bind_brief(logger, "brief-123")
    obs.bind_request(logger, "req-9")
    logger.info("one")
    logger.warning("two")
    logger.error("three")
    out = lines(stream)
    assert len(out) == 3
    assert all(x["briefId"] == "brief-123" and x["requestId"] == "req-9" for x in out)


def test_email_addresses_in_messages_are_redacted():
    logger, stream = make_logger("svc-3")
    logger.info("Checking Jane.Doe+test@Delta.com and bob@example.co.uk now")
    text = stream.getvalue()
    assert "Jane.Doe" not in text and "@Delta.com" not in text and "bob@example" not in text
    assert "[email]" in text


def test_invite_text_and_other_sensitive_fields_are_redacted_in_extra_data():
    logger, stream = make_logger("svc-4")
    logger.info("saved", extra={
        "inviteText": "Subject: Discovery call with secret details",
        "attendees": [{"name": "Jane", "email": "jane@delta.com"}],
        "email": "jane@delta.com",
        "token": "abc",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig",
        "step": "Parsing",
    })
    text = stream.getvalue()
    for secret in ("secret details", "Jane", "jane@delta.com", "eyJhbGci", "abc"):
        assert secret not in text, secret
    (line,) = lines(stream)
    assert line["step"] == "Parsing"                      # harmless fields stay
    assert line["inviteText"] == obs.REDACTED


def test_nested_sensitive_fields_are_redacted():
    cleaned = obs.scrub({"outer": {"Invite_Text": "x", "ok": "fine", "list": ["a@b.com", {"notes": "n"}]}})
    assert cleaned["outer"]["Invite_Text"] == obs.REDACTED
    assert cleaned["outer"]["ok"] == "fine"
    assert cleaned["outer"]["list"][0] == "[email]" and cleaned["outer"]["list"][1] == {"notes": obs.REDACTED}


def test_bearer_tokens_and_jwts_in_text_are_redacted():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
    assert jwt not in obs.scrub(f"token is {jwt}")
    assert "abc123" not in obs.scrub("Authorization: Bearer abc123")


def test_exceptions_are_logged_without_emails():
    logger, stream = make_logger("svc-5")
    address = "jane" + "@delta.com"      # built at run time, like real data (not a literal in the source line)
    try:
        raise ValueError("bad value for " + address)
    except ValueError:
        logger.exception("failed")
    text = stream.getvalue()
    (line,) = lines(stream)
    assert "jane@delta.com" not in text
    assert line["exception_name"] == "ValueError" and "[email]" in text


def test_format_arguments_are_scrubbed():
    logger, stream = make_logger("svc-6")
    logger.info("user %s asked", "jane@delta.com")
    assert "jane@delta.com" not in stream.getvalue()


def test_no_double_filters_when_the_logger_is_requested_twice():
    stream = io.StringIO()
    obs.get_logger(service="svc-7", stream=stream)
    logger = obs.get_logger(service="svc-7", stream=stream)
    handler = logger.registered_handler
    assert sum(isinstance(f, obs.RedactingFilter) for f in handler.filters) == 1


# --- metrics ---------------------------------------------------------------------------------------
def emf_lines(capsys) -> list[dict]:
    return [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip().startswith("{")]


def test_metric_names_are_the_three_mvp_metrics():
    assert obs.METRIC_NAMES == {"BriefGenerated", "BedrockCalls", "BedrockThrottled"}


def test_metrics_are_written_as_emf_with_the_right_names(capsys):
    sink = obs.PowertoolsMetrics(Metrics(namespace="TestNs", service="svc"))
    sink.incr("BedrockCalls")
    sink.incr("BedrockCalls", 2)
    sink.incr("BedrockThrottled")
    sink.incr("BriefGenerated")
    sink.flush()
    (doc,) = emf_lines(capsys)
    declared = {m["Name"] for m in doc["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
    assert declared == {"BedrockCalls", "BedrockThrottled", "BriefGenerated"}
    assert doc["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "TestNs"
    assert doc["BedrockCalls"] == [1, 2] or doc["BedrockCalls"] == 3 or sum(doc["BedrockCalls"]) == 3


def test_unknown_metric_names_are_refused():
    sink = obs.PowertoolsMetrics(Metrics(namespace="TestNs", service="svc"))
    with pytest.raises(ValueError):
        sink.incr("BedrockCall")          # typo
    with pytest.raises(ValueError):
        sink.incr("ResearchLatencyMs")    # added by the stretch task, not now


def test_flush_with_nothing_collected_writes_nothing(capsys):
    obs.PowertoolsMetrics(Metrics(namespace="TestNs", service="svc")).flush()
    assert emf_lines(capsys) == []


def test_the_sink_fits_the_bedrock_client(capsys):
    """The real Bedrock client counts attempts and throttles through this sink."""
    from botocore.exceptions import ClientError

    clock = FakeClock()
    script = [ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse"),
              {"output": {"message": {"content": [{"text": '{"a": "b"}'}]}}, "usage": {}}]

    class Runtime:
        def converse(self, **kw):
            item = script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    sink = obs.PowertoolsMetrics(Metrics(namespace="TestNs", service="svc"))
    assert callable(getattr(sink, "incr", None))      # the interface the client needs
    client = BedrockClient(runtime=Runtime(), bucket=TokenBucket(clock=clock.time, sleep=clock.sleep), metrics=sink,
                           env={"BEDROCK_MODEL_HAIKU": "m"}, sleep=clock.sleep, rng=lambda: 0.0)
    client.converse_json(model="haiku", system="s", user="u", max_tokens=10,
                         schema={"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}})
    sink.flush()
    (doc,) = emf_lines(capsys)
    assert sum(doc["BedrockCalls"]) == 2 if isinstance(doc["BedrockCalls"], list) else doc["BedrockCalls"] == 2
    assert doc["BedrockThrottled"] == 1 or sum(doc["BedrockThrottled"]) == 1
