"""A full in-memory backend (moto DynamoDB and SQS) for worker, handler, and runner tests."""
from __future__ import annotations

import contextlib
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import boto3
from moto import mock_aws

from backend.src.lib.brief_store import BRIEFS_TABLE_DEFINITION, BriefStore
from backend.src.lib.profiles import load_profiles
from backend.src.services import pipeline
from backend.src.services.case_study_matcher import load_case_studies
from backend.src.services.offline_model import OfflineModel
from backend.src.services.research import ResearchService
from backend.src.services.research_provider import FixtureProvider
from backend.src.services.rules import RulesStore
from backend.tests.fakes import FakeClock

RECORDED = Path(__file__).resolve().parent / "fixtures" / "research"
INVITES = Path(__file__).resolve().parents[2] / "data" / "sample_invites"

RULES_DEF = {
    "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "ruleId", "KeyType": "RANGE"}],
    "AttributeDefinitions": [{"AttributeName": "userId", "AttributeType": "S"}, {"AttributeName": "ruleId", "AttributeType": "S"}],
    "BillingMode": "PAY_PER_REQUEST",
}
CACHE_DEF = {
    "KeySchema": [{"AttributeName": "companyDomain", "KeyType": "HASH"}],
    "AttributeDefinitions": [{"AttributeName": "companyDomain", "AttributeType": "S"}],
    "BillingMode": "PAY_PER_REQUEST",
}


@dataclass
class Env:
    store: BriefStore
    deps: pipeline.Deps
    clock: FakeClock
    model: Any
    tables: dict[str, Any]
    queue_url: str
    sqs: Any
    events: list

    def sent_messages(self) -> list[dict[str, Any]]:
        import json

        out = []
        while True:
            resp = self.sqs.receive_message(QueueUrl=self.queue_url, MaxNumberOfMessages=10)
            msgs = resp.get("Messages", [])
            if not msgs:
                return out
            for m in msgs:
                out.append(json.loads(m["Body"]))
                self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=m["ReceiptHandle"])


@contextlib.contextmanager
def backend(model: Any | None = None, provider: Any | None = None) -> Iterator[Env]:
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        tables = {
            "Briefs": ddb.create_table(TableName="Briefs", **BRIEFS_TABLE_DEFINITION),
            "Rules": ddb.create_table(TableName="Rules", **RULES_DEF),
            "ResearchCache": ddb.create_table(TableName="ResearchCache", **CACHE_DEF),
        }
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue_url = sqs.create_queue(QueueName="jobs")["QueueUrl"]
        clock = FakeClock(start=1_790_000_000.0)
        ids = itertools.count(1)
        store = BriefStore(tables["Briefs"], clock=clock.time, id_factory=lambda: f"{next(ids):032x}")
        model = model or OfflineModel()
        events: list = []
        deps = pipeline.Deps(
            store=store,
            research=ResearchService(model, provider or FixtureProvider(RECORDED), tables["ResearchCache"], clock=clock.time),
            bedrock=model,
            rules=RulesStore(tables["Rules"], clock=clock.time),
            studies=load_case_studies(),
            profiles=load_profiles(),
            log=lambda event, data: events.append((event, data)),
        )
        yield Env(store, deps, clock, model, tables, queue_url, sqs, events)


def invite_text(name: str) -> str:
    return (INVITES / name).read_text(encoding="utf-8")
