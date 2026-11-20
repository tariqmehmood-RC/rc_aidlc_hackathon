import json
from pathlib import Path
from urllib.parse import quote

import pytest

from backend.src.lib.http_fetch import FetchResult, html_to_text
from backend.src.services import research_provider as rp

FIX = Path(__file__).resolve().parent / "fixtures"
WEB = FIX / "web"
RECORDED = FIX / "research"
SAMPLE = json.loads((Path(__file__).resolve().parents[2] / "data" / "sample_invites" / "expected.json").read_text())

NAME, DOMAIN = "Example Air", "example-air.com"
SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/page?q=Example%20Air&limit=5"
PAGE_BAND = "https://en.wikipedia.org/api/rest_v1/page/html/" + quote("Example_Air_(band)", safe="")
PAGE_AIR = "https://en.wikipedia.org/api/rest_v1/page/html/Example_Air"
SUMMARY_AIR = "https://en.wikipedia.org/api/rest_v1/page/summary/Example_Air"
SUMMARY_BAND = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote("Example_Air_(band)", safe="")
WIKI_URL = "https://en.wikipedia.org/wiki/Example_Air"
HOME = "https://example-air.com/"
HOME_FINAL = "https://www.example-air.com/"
ABOUT = "https://www.example-air.com/about-us/"
NEWS = rp.NEWS_RSS.format(q="Example%20Air")


class FakeFetcher:
    """Serves the small hand-written pages in fixtures/web. Unknown URLs give a 404 failure."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.requested: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.requested.append(url)
        route = self.routes.get(url)
        if route is None:
            return FetchResult(url, url, ok=False, status=404, error="http_404")
        if isinstance(route, int):
            return FetchResult(url, url, ok=False, status=route, error=f"http_{route}")
        filename, final = route if isinstance(route, tuple) else (route, url)
        body = (WEB / filename).read_text(encoding="utf-8")
        text = html_to_text(body) if filename.endswith(".html") else body
        return FetchResult(url, final, ok=True, status=200, text=text, body=body)


def full_routes() -> dict[str, object]:
    return {
        SEARCH: "wikipedia_search.json",
        PAGE_BAND: "wikipedia_page_band.html",
        PAGE_AIR: "wikipedia_page_airline.html",
        SUMMARY_AIR: "wikipedia_summary_airline.json",
        HOME: ("homepage.html", HOME_FINAL),
        ABOUT: "about.html",
        NEWS: "news.rss",
    }


def run(routes=None, name=NAME, domain=DOMAIN, **kw):
    fetcher = FakeFetcher(routes if routes is not None else full_routes())
    kw.setdefault("sleep", lambda s: None)
    return rp.PublicWebProvider(fetcher, **kw).research(name, domain), fetcher


def kinds(raw):
    return [d.kind for d in raw.documents]


# --- the happy path ---------------------------------------------------------------------------
def test_collects_site_wikipedia_and_news_documents_with_source_urls():
    raw, _ = run()
    assert {"homepage", "about", "wikipedia_summary", "wikipedia_page", "news"} <= set(kinds(raw))
    for d in raw.documents:
        assert d.url.startswith("https://") and d.text.strip()
    by_kind = {d.kind: d for d in raw.documents}
    assert by_kind["homepage"].url == HOME_FINAL
    assert by_kind["about"].url == ABOUT
    assert by_kind["wikipedia_summary"].url == WIKI_URL


def test_wikipedia_candidate_is_chosen_by_matching_the_domain():
    raw, fetcher = run()
    assert raw.match_confidence == "confirmed"
    page = next(d for d in raw.documents if d.kind == "wikipedia_page")
    assert "airline" in page.text and "band" not in page.text
    assert PAGE_BAND in fetcher.requested and PAGE_AIR in fetcher.requested  # the band was checked first and rejected


def _no_wiki_page_mentions_the_domain():
    routes = full_routes()
    routes[PAGE_AIR] = "wikipedia_page_band.html"  # no page mentions example-air.com
    routes[SUMMARY_BAND] = "wikipedia_summary_airline.json"
    return routes


def test_without_a_domain_match_or_a_site_the_first_name_match_is_used_and_marked_unverified():
    routes = _no_wiki_page_mentions_the_domain()
    del routes[HOME]  # the company site does not load either
    raw, _ = run(routes)
    assert raw.match_confidence == "unverified_match"
    assert any(d.kind == "wikipedia_page" for d in raw.documents)


def test_a_wikipedia_page_that_only_shares_the_name_is_dropped_when_the_site_loads():
    # "Royal Cyber" found the "Royal (cyber gang)" page, which never mentions royalcyber.com.
    raw, _ = run(_no_wiki_page_mentions_the_domain())
    assert raw.match_confidence == "confirmed"
    assert not any(d.kind.startswith("wikipedia") for d in raw.documents)
    assert not any("wikipedia.org" in u for u in raw.usable_urls)
    assert not any("wikipedia.org" in s.url and s.status == "ok" for s in raw.sources)
    assert {"homepage", "about"} <= set(kinds(raw))


def test_unrelated_search_results_are_ignored():
    routes = {SEARCH: "wikipedia_search.json"}  # only an unrelated page would be left after name filtering
    raw, fetcher = run(routes, name="Unrelated Topic")
    # the only name match is "Unrelated Topic" itself, but its page is a 404 here, so no wikipedia documents
    assert not any(d.kind.startswith("wikipedia") for d in raw.documents)
    assert all("Example_Air" not in u for u in fetcher.requested)


def test_homepage_about_link_must_be_on_the_same_site():
    raw, fetcher = run()
    assert "https://other-site.com/about" not in fetcher.requested
    assert ABOUT in fetcher.requested


def test_homepage_text_is_plain_text():
    raw, _ = run()
    home = next(d for d in raw.documents if d.kind == "homepage")
    assert "Fly with Example Air" in home.text
    assert "<" not in home.text and ".x{}" not in home.text


# --- news ----------------------------------------------------------------------------------------
def test_news_is_limited_to_three_newest_first_with_real_links_only():
    raw, _ = run()
    assert [n.title for n in raw.news] == [
        "Example Air newest story - The Journal", "Example Air second newest - Biz Times",
        "Example Air middle story - Aviation Weekly"]
    assert [n.date for n in raw.news] == ["2026-11-19", "2026-11-18", "2026-11-10"]
    assert all(n.url.startswith("https://") for n in raw.news)
    news_docs = [d for d in raw.documents if d.kind == "news"]
    assert len(news_docs) == 3


def test_news_request_sends_locale_parameters():
    _, fetcher = run()
    assert NEWS in fetcher.requested and "hl=en-US&gl=US&ceid=US:en" in NEWS


def test_hostile_xml_does_not_break_research():
    routes = full_routes()
    routes[NEWS] = "evil.rss"  # declares entities (an expansion attack), which must be refused
    raw, _ = run(routes)
    assert raw.news == []
    assert any(d.kind == "homepage" for d in raw.documents)


# --- failures ------------------------------------------------------------------------------------
def test_one_failing_source_does_not_stop_the_others():
    routes = full_routes()
    routes[HOME] = 403  # Cloudflare style block
    raw, _ = run(routes)
    assert "homepage" not in kinds(raw)
    assert {"wikipedia_summary", "news"} <= set(kinds(raw))
    assert any(s.url == HOME and s.status == "failed" for s in raw.sources)


def test_all_sources_failing_returns_an_empty_result_without_raising():
    raw, _ = run({})
    assert raw.documents == [] and raw.news == []
    assert raw.usable_urls == set()
    assert all(s.status in ("failed", "skipped") for s in raw.sources)


def test_garbage_wikipedia_responses_are_tolerated():
    routes = full_routes()
    routes[SEARCH] = "homepage.html"  # not JSON
    raw, _ = run(routes)
    assert not any(d.kind.startswith("wikipedia") for d in raw.documents)
    assert "homepage" in kinds(raw)


def test_apex_domain_failure_falls_back_to_the_www_host():
    class Flaky(FakeFetcher):
        def fetch(self, url):
            if url == HOME:
                self.requested.append(url)
                return FetchResult(url, url, ok=False, error="network_error")
            return super().fetch(url)

    routes = full_routes()
    routes["https://www.example-air.com/"] = ("homepage.html", HOME_FINAL)
    fetcher = Flaky(routes)
    raw = rp.PublicWebProvider(fetcher).research(NAME, DOMAIN)
    assert "homepage" in kinds(raw)
    assert fetcher.requested.index(HOME) < fetcher.requested.index("https://www.example-air.com/")


def test_a_403_is_not_retried_on_the_www_host():
    routes = full_routes()
    routes[HOME] = 403
    _, fetcher = run(routes)
    assert fetcher.requested.count(HOME) == 1
    assert not any(u == "https://www.example-air.com/" for u in fetcher.requested)


class RateLimited(FakeFetcher):
    """Answers 429 (with Retry-After) the first `times` times for one URL."""

    def __init__(self, routes, url, times, retry_after=None):
        super().__init__(routes)
        self.limited_url, self.left, self.retry_after = url, times, retry_after

    def fetch(self, url):
        if url == self.limited_url and self.left > 0:
            self.left -= 1
            self.requested.append(url)
            return FetchResult(url, url, ok=False, status=429, error="http_429", retry_after=self.retry_after)
        return super().fetch(url)


def test_a_429_is_waited_out_and_retried():
    waits = []
    fetcher = RateLimited(full_routes(), SEARCH, times=1, retry_after=2.0)
    raw = rp.PublicWebProvider(fetcher, sleep=waits.append).research(NAME, DOMAIN)
    assert fetcher.requested.count(SEARCH) == 2
    assert waits == [2.0]
    assert "wikipedia_summary" in kinds(raw)


def test_retry_after_wait_is_capped_and_retries_stop_after_two():
    waits = []
    fetcher = RateLimited(full_routes(), SEARCH, times=10, retry_after=120.0)
    raw = rp.PublicWebProvider(fetcher, sleep=waits.append).research(NAME, DOMAIN)
    assert fetcher.requested.count(SEARCH) == 3          # first try plus two retries
    assert waits == [rp.MAX_RETRY_WAIT_S, rp.MAX_RETRY_WAIT_S]
    assert not any(d.kind.startswith("wikipedia") for d in raw.documents)
    assert any(s.url == SEARCH and s.status == "failed" for s in raw.sources)


def test_other_errors_are_not_retried_after_waiting():
    waits = []
    routes = full_routes()
    routes[SEARCH] = 500
    fetcher = FakeFetcher(routes)
    rp.PublicWebProvider(fetcher, sleep=waits.append).research(NAME, DOMAIN)
    assert fetcher.requested.count(SEARCH) == 1 and waits == []


def test_no_domain_skips_the_website_and_cannot_confirm_a_match():
    raw, fetcher = run(domain=None)
    assert "homepage" not in kinds(raw)
    assert any(s.status == "skipped" for s in raw.sources)
    assert raw.match_confidence == "unverified_match"
    assert HOME not in fetcher.requested


def test_no_name_skips_wikipedia():
    raw, fetcher = run(name=None)
    assert not any("wikipedia" in u for u in fetcher.requested)
    assert "homepage" in kinds(raw)


def test_site_only_result_counts_as_confirmed_when_no_wikipedia_page_exists():
    routes = {HOME: ("homepage.html", HOME_FINAL), NEWS: "news.rss"}
    raw, _ = run(routes)
    assert raw.match_confidence == "confirmed"


# --- limits --------------------------------------------------------------------------------------
def test_document_text_is_cut_to_the_limit():
    raw, _ = run(max_doc_chars=40)
    for d in raw.documents:
        if d.kind in ("homepage", "about", "wikipedia_summary"):
            assert len(d.text) <= 45


def test_only_fetched_urls_are_usable_for_citation():
    raw, _ = run()
    assert raw.usable_urls == {d.url for d in raw.documents}
    assert "https://example.invalid/made-up" not in raw.usable_urls


def test_query_values_are_url_encoded():
    _, fetcher = run(name="A&B Corp?", domain="ab.com")
    assert any("q=A%26B%20Corp%3F" in u for u in fetcher.requested)


# --- serialization and the fixture provider ---------------------------------------------------------
def test_raw_research_round_trips_through_json():
    raw, _ = run()
    again = rp.RawResearch.from_dict(json.loads(json.dumps(raw.to_dict())))
    assert again == raw


def test_fixture_provider_returns_an_empty_result_for_a_missing_fixture(tmp_path):
    raw = rp.FixtureProvider(tmp_path).research("Nobody Inc", "nobody.example")
    assert raw.documents == [] and raw.sources[0].status == "failed"


def test_fixture_key():
    assert rp.FixtureProvider.fixture_key("Delta Air Lines", "Delta.com") == "delta.com"
    assert rp.FixtureProvider.fixture_key("Delta Air Lines", None) == "deltaairlines"


@pytest.mark.parametrize("name", sorted(SAMPLE))
def test_recorded_fixtures_exist_for_the_sample_invites(name):
    domain = SAMPLE[name]["company"]["domain"]
    raw = rp.FixtureProvider(RECORDED).research(SAMPLE[name]["company"]["name"], domain)
    assert raw.documents, f"no recorded research for {domain}; run scripts/record_fixtures.py"
    assert all(d.url.startswith("https://") for d in raw.documents)
    assert raw.usable_urls
    assert len(raw.news) <= 3


# --- news quality ------------------------------------------------------------------------------
def test_news_that_does_not_name_the_company_is_dropped_even_if_the_outlet_does():
    raw, _ = run()
    assert all("regional airport" not in n.title for n in raw.news)


def test_duplicate_stories_are_removed_by_headline():
    raw, _ = run()
    titles = [rp.headline(n.title) for n in raw.news]
    assert titles.count("Example Air newest story") == 1


@pytest.mark.parametrize("name,domain,expected", [
    ("Marriott International", "marriott.com", ["Marriott International", "Marriott"]),
    ("Delta Air Lines", "delta.com", ["Delta Air Lines", "Delta"]),
    ("Allstate", "allstate.com", ["Allstate"]),
    (None, "duolingo.com", ["duolingo"]),
    ("3M", "3m.com", ["3M"]),
    ("Royal Cyber", "royalcyber.com", ["Royal Cyber", "royalcyber"]),
])
def test_company_terms(name, domain, expected):
    assert rp.company_terms(name, domain) == expected


@pytest.mark.parametrize("text,ok", [
    ("Delta cuts 10 international routes", True),
    ("A plane in a Delta 737's path", True),
    ("Busiest month ever at Sonoma County Airport", False),
    ("Deltamax launches new product", False),            # whole words only
    ("DELTA shares rise", True),
])
def test_mentions_company_matches_whole_words(text, ok):
    assert rp.mentions_company(text, rp.company_terms("Delta Air Lines", "delta.com")) is ok


def test_sources_are_fetched_in_parallel_but_merged_in_a_fixed_order():
    import threading
    import time as _time

    started = []

    class Slow(FakeFetcher):
        def fetch(self, url):
            started.append((_time.monotonic(), threading.current_thread().name))
            _time.sleep(0.05)
            return super().fetch(url)

    t0 = _time.monotonic()
    raw = rp.PublicWebProvider(Slow(full_routes()), sleep=lambda s: None).research(NAME, DOMAIN)
    elapsed = _time.monotonic() - t0
    assert len({name for _, name in started}) >= 2          # more than one thread did work
    assert elapsed < 0.05 * len(started)                      # faster than one fetch after another
    kinds_order = [d.kind for d in raw.documents]
    assert kinds_order.index("wikipedia_summary") < kinds_order.index("homepage") < kinds_order.index("news")


@pytest.mark.parametrize("text,ok", [
    ("Royal Cyber: Transforming Your Business with Big Data, IoT & Cloud Services", True),
    ("RoyalCyber named a ServiceNow partner", True),
    ("OKNG, Royal Brunei Armed Forces strengthen cyber readiness", False),
    ("Mount Royal University student portal reopens after June cyber attack", False),
])
def test_news_for_a_two_word_name_needs_the_full_name(text, ok):
    assert rp.mentions_company(text, rp.company_terms("Royal Cyber", "royalcyber.com")) is ok
