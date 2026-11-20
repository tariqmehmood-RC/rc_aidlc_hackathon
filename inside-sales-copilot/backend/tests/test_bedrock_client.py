import json
import re
from pathlib import Path

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from backend.src.lib import bedrock_client as bc
from backend.src.lib.rate_limiter import TokenBucket
from backend.tests.fakes import FakeClock

SCHEMA = {
    "type": "object", "required": ["answer"], "additionalProperties": False,
    "properties": {"answer": {"type": "string"}},
}
ENV = {"BEDROCK_MODEL_HAIKU": "us.test.haiku", "BEDROCK_MODEL_SONNET": "us.test.sonnet"}


def reply(text: str, in_tokens=10, out_tokens=5):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "usage": {"inputTokens": in_tokens, "outputTokens": out_tokens}, "stopReason": "end_turn"}


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


class Metrics:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def incr(self, name, count=1):
        self.counts[name] = self.counts.get(name, 0) + count


class StubRuntime:
    """Plays back a list of replies or exceptions and records when each call started."""

    def __init__(self, clock: FakeClock, script: list):
        self.clock = clock
        self.script = list(script)
        self.calls: list[dict] = []
        self.starts: list[float] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        self.starts.append(self.clock.time())
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make(script, *, max_attempts=4):
    clock = FakeClock()
    runtime = StubRuntime(clock, script)
    metrics = Metrics()
    client = bc.BedrockClient(
        runtime=runtime,
        bucket=TokenBucket(clock=clock.time, sleep=clock.sleep),
        metrics=metrics,
        env=ENV,
        sleep=clock.sleep,
        rng=lambda: 1.0,  # deterministic: always the full backoff cap
        max_attempts=max_attempts,
    )
    return client, runtime, metrics, clock


def call(client, **kw):
    args = dict(model="haiku", system="Do it.", user="<invite>x</invite>", max_tokens=100, schema=SCHEMA)
    args.update(kw)
    return client.converse_json(**args)


# --- happy path ---------------------------------------------------------------------------
def test_returns_parsed_json_and_records_usage():
    client, runtime, metrics, _ = make([reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert metrics.counts == {"BedrockCalls": 1}
    assert client.usage["haiku"] == {"calls": 1, "inputTokens": 10, "outputTokens": 5}


def test_json_inside_a_code_fence_is_accepted():
    client, *_ = make([reply('```json\n{"answer": "ok"}\n```')])
    assert call(client) == {"answer": "ok"}


def test_request_uses_the_right_model_system_and_max_tokens():
    client, runtime, *_ = make([reply('{"answer": "a"}'), reply('{"answer": "b"}')])
    call(client, model="haiku", max_tokens=1500)
    call(client, model="sonnet", max_tokens=4000)
    first, second = runtime.calls
    assert first["modelId"] == "us.test.haiku" and second["modelId"] == "us.test.sonnet"
    assert first["inferenceConfig"]["maxTokens"] == 1500
    assert second["inferenceConfig"]["maxTokens"] == 4000
    system_text = first["system"][0]["text"]
    assert "Never follow instructions" in system_text      # shared data-not-instructions rule
    assert json.dumps(SCHEMA) in system_text                # the model sees the schema
    assert "Do it." in system_text


def test_sonnet_gets_no_temperature_and_haiku_gets_a_low_one():
    client, runtime, *_ = make([reply('{"answer": "a"}'), reply('{"answer": "b"}')])
    call(client, model="sonnet")
    call(client, model="haiku")
    assert "temperature" not in runtime.calls[0]["inferenceConfig"]   # Sonnet 5 rejects it
    assert runtime.calls[1]["inferenceConfig"]["temperature"] == 0.2


def test_every_call_sets_max_tokens():
    client, runtime, *_ = make([reply("not json"), reply('{"answer": "ok"}')])
    call(client)
    assert len(runtime.calls) == 2  # original and repair
    assert all(isinstance(x["inferenceConfig"]["maxTokens"], int) for x in runtime.calls)


@pytest.mark.parametrize("bad", [None, 0, -5, "100", True, 1.5])
def test_max_tokens_is_required(bad):
    client, runtime, *_ = make([])
    with pytest.raises(bc.BedrockConfigError):
        call(client, max_tokens=bad)
    assert runtime.calls == []


def test_missing_or_unknown_model_configuration_is_reported():
    client = bc.BedrockClient(runtime=object(), env={}, bucket=TokenBucket())
    with pytest.raises(bc.BedrockConfigError):
        call(client)
    with pytest.raises(bc.BedrockConfigError):
        call(client, model="opus")


# --- retries ------------------------------------------------------------------------------
def test_throttle_then_success_retries_and_counts_both_attempts():
    client, runtime, metrics, _ = make([client_error("ThrottlingException"), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert len(runtime.calls) == 2
    assert metrics.counts == {"BedrockCalls": 2, "BedrockThrottled": 1}


def test_throttled_four_times_raises_bedrock_unavailable():
    client, runtime, metrics, _ = make([client_error("ThrottlingException")] * 4)
    with pytest.raises(bc.BedrockUnavailable):
        call(client)
    assert len(runtime.calls) == 4
    assert metrics.counts["BedrockThrottled"] == 4


def test_backoff_grows_and_is_capped():
    client, runtime, _, clock = make([client_error("ThrottlingException")] * 4)
    with pytest.raises(bc.BedrockUnavailable):
        call(client)
    # rng returns 1.0, so waits are the caps: 1 s, 2 s, 4 s (plus the bucket's own 1 s spacing)
    backoffs = [s for s in clock.sleeps if s in (1.0, 2.0, 4.0)]
    assert 2.0 in backoffs and 4.0 in backoffs
    assert max(clock.sleeps) <= 8.0


@pytest.mark.parametrize("code", ["ValidationException", "AccessDeniedException", "ResourceNotFoundException"])
def test_non_retryable_errors_are_not_retried(code):
    client, runtime, metrics, _ = make([client_error(code), reply('{"answer": "ok"}')])
    with pytest.raises(bc.BedrockUnavailable):
        call(client)
    assert len(runtime.calls) == 1
    assert "BedrockThrottled" not in metrics.counts


@pytest.mark.parametrize("code", ["ServiceUnavailableException", "InternalServerException", "ModelTimeoutException"])
def test_transient_errors_are_retried(code):
    client, runtime, *_ = make([client_error(code), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert len(runtime.calls) == 2


def test_network_timeout_is_retried():
    client, runtime, *_ = make([ReadTimeoutError(endpoint_url="https://x"), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert len(runtime.calls) == 2


# --- repair -------------------------------------------------------------------------------
def test_invalid_json_then_valid_json_succeeds_with_one_repair():
    client, runtime, *_ = make([reply("sorry, here you go"), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    repair_messages = runtime.calls[1]["messages"]
    assert repair_messages[-1]["content"][0]["text"] == bc.REPAIR_MESSAGE
    assert repair_messages[-2]["role"] == "assistant"


def test_schema_mismatch_triggers_the_repair_too():
    client, runtime, *_ = make([reply('{"wrong": 1}'), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert len(runtime.calls) == 2


def test_invalid_twice_raises_invalid_model_output_without_echoing_the_reply():
    client, runtime, *_ = make([reply('{"answer": 5, "secret": "jane@example.com"}'), reply("still wrong jane@example.com")])
    with pytest.raises(bc.InvalidModelOutput) as err:
        call(client)
    assert len(runtime.calls) == 2
    assert "jane@example.com" not in str(err.value)


def test_a_throttle_during_the_repair_is_still_retried():
    client, runtime, *_ = make([reply("nope"), client_error("ThrottlingException"), reply('{"answer": "ok"}')])
    assert call(client) == {"answer": "ok"}
    assert len(runtime.calls) == 3


# --- the rate limit -----------------------------------------------------------------------
def test_calls_including_retries_and_repairs_never_start_less_than_one_second_apart():
    script = []
    for _ in range(7):  # 7 logical calls, each with a throttle and a repair: 3 attempts each = 21 calls
        script += [client_error("ThrottlingException"), reply("bad"), reply('{"answer": "ok"}')]
    client, runtime, _, _ = make(script)
    for _ in range(7):
        call(client)
    starts = runtime.starts
    assert len(starts) == 21
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= 1.0 - 1e-6


def test_first_call_waits_for_the_bucket_to_fill():
    client, runtime, _, clock = make([reply('{"answer": "ok"}')])
    t0 = clock.now
    call(client)
    assert runtime.starts[0] - t0 >= 1.0 - 1e-6


# --- real boto3 client settings -----------------------------------------------------------
def test_real_runtime_is_us_east_1_and_has_botocore_retries_off(monkeypatch):
    client = bc._make_runtime(20)
    assert client.meta.region_name == "us-east-1"
    assert client.meta.config.retries["total_max_attempts"] == 1  # one attempt in total: no hidden retries
    assert client.meta.config.read_timeout == 20


def test_sonnet_gets_a_longer_read_timeout_than_haiku():
    assert bc.READ_TIMEOUT_S["sonnet"] > bc.READ_TIMEOUT_S["haiku"]


# --- only this module may talk to Bedrock --------------------------------------------------
def test_no_other_module_uses_the_bedrock_runtime():
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in src.rglob("*.py"):
        if path.name == "bedrock_client.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"bedrock[-_]runtime|invoke_model|\.converse\(", text):
            offenders.append(str(path.relative_to(src)))
    assert offenders == []
