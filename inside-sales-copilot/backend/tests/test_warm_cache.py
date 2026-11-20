import importlib.util
import io
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from backend.src.services.offline_model import OfflineModel
from backend.src.services.research import ResearchService
from backend.src.services.research_provider import FixtureProvider, RawResearch
from backend.tests.env_helpers import CACHE_DEF, RECORDED

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("warm_cache", ROOT / "scripts" / "warm_cache.py")
warm_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(warm_cache)
DEMO = [ROOT / p for p in warm_cache.DEMO_INVITES]


@pytest.fixture()
def table():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1").create_table(TableName="ResearchCache", **CACHE_DEF)


class Counting:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def research(self, name, domain):
        self.calls += 1
        return self.inner.research(name, domain)


def test_demo_invites_are_researched_and_stored(table):
    model = OfflineModel()
    out = io.StringIO()
    results = warm_cache.warm(DEMO, model, ResearchService(model, FixtureProvider(RECORDED), table), out=out)
    assert [r["status"] for r in results] == ["warmed", "warmed"]
    assert {r["key"] for r in results} == {"allstate.com", "delta.com"}
    for key in ("allstate.com", "delta.com"):
        assert table.get_item(Key={"companyDomain": key}).get("Item")
    assert "Allstate (allstate.com) researched" in out.getvalue()


def test_no_brief_is_written(table):
    from backend.src.services import brief_writer, case_study_matcher

    model = OfflineModel()
    seen = []
    real = model.converse_json
    model.converse_json = lambda **kw: seen.append(kw["schema"]) or real(**kw)
    warm_cache.warm(DEMO, model, ResearchService(model, FixtureProvider(RECORDED), table), out=io.StringIO())
    assert brief_writer.P4_SCHEMA not in seen and case_study_matcher.P3_SCHEMA not in seen
    assert len(seen) == 4  # parse and research for each of the two invites


def test_a_second_run_uses_the_cache_and_refresh_researches_again(table):
    model = OfflineModel()
    provider = Counting(FixtureProvider(RECORDED))
    svc = ResearchService(model, provider, table)
    warm_cache.warm(DEMO[:1], model, svc, out=io.StringIO())
    assert warm_cache.warm(DEMO[:1], model, svc, out=io.StringIO())[0]["status"] == "cached"
    assert provider.calls == 1
    assert warm_cache.warm(DEMO[:1], model, svc, refresh=True, out=io.StringIO())[0]["status"] == "warmed"
    assert provider.calls == 2


def test_a_company_with_no_public_information_is_reported(table):
    class Empty:
        def research(self, name, domain):
            return RawResearch()

    model = OfflineModel()
    results = warm_cache.warm(DEMO[:1], model, ResearchService(model, Empty(), table), out=io.StringIO())
    assert results[0]["status"] == "no_public_info"


def test_main_needs_a_table_name(monkeypatch):
    monkeypatch.delenv("RESEARCH_CACHE_TABLE", raising=False)
    with pytest.raises(SystemExit):
        warm_cache.main([])
