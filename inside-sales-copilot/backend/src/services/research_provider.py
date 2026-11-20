"""Where company research comes from (requirements R3.1, R3.13, R3.15; design 8.1).

`ResearchProvider` is the seam: today `PublicWebProvider` reads the company site, Wikipedia
and Google News. A later provider (AgentCore Browser, a search API) only has to return the
same `RawResearch`. `FixtureProvider` replays recorded results for tests and the local runner.
"""
from __future__ import annotations

import datetime
import email.utils
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import quote, urljoin, urlsplit

from defusedxml import ElementTree as SafeET

from ..lib import constants as c
from ..lib.http_fetch import FetchResult, Fetcher

MAX_DOC_CHARS = 4000       # per document, to keep the model prompt small
MAX_WIKI_PAGE_CHARS = 6000
MAX_RATE_LIMIT_RETRIES = 2
MAX_RETRY_WAIT_S = 3.0
WIKI_API = "https://en.wikipedia.org"
NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

KIND_HOMEPAGE, KIND_ABOUT = "homepage", "about"
KIND_WIKI_SUMMARY, KIND_WIKI_PAGE, KIND_NEWS = "wikipedia_summary", "wikipedia_page", "news"


@dataclass(frozen=True)
class SourceDoc:
    url: str
    kind: str
    text: str
    title: str | None = None


@dataclass(frozen=True)
class NewsItem:
    title: str
    date: str | None  # YYYY-MM-DD
    url: str


@dataclass(frozen=True)
class SourceStatus:
    url: str
    status: str  # ok | failed | skipped


@dataclass
class RawResearch:
    documents: list[SourceDoc] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
    sources: list[SourceStatus] = field(default_factory=list)
    match_confidence: str = "unverified_match"  # confirmed | unverified_match

    @property
    def usable_urls(self) -> set[str]:
        """URLs of documents that were actually fetched. Only these may be cited."""
        return {d.url for d in self.documents}

    def to_dict(self) -> dict[str, Any]:
        return {
            "documents": [d.__dict__ for d in self.documents],
            "news": [n.__dict__ for n in self.news],
            "sources": [s.__dict__ for s in self.sources],
            "match_confidence": self.match_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RawResearch":
        return cls(
            documents=[SourceDoc(**x) for x in d.get("documents", [])],
            news=[NewsItem(**x) for x in d.get("news", [])],
            sources=[SourceStatus(**x) for x in d.get("sources", [])],
            match_confidence=d.get("match_confidence", "unverified_match"),
        )


class ResearchProvider(Protocol):
    def research(self, company_name: str | None, domain: str | None) -> RawResearch: ...


# --- helpers ---------------------------------------------------------------------------------
def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _names_overlap(company: str, title: str) -> bool:
    a, b = _key(company), _key(re.sub(r"\(.*?\)", "", title))
    return bool(a) and bool(b) and (a in b or b in a)


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def _rss_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.date().isoformat()


def _same_site(url: str, domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


_SUFFIX_WORDS = {"inc", "incorporated", "corp", "corporation", "company", "co", "llc", "ltd", "limited",
                 "plc", "group", "holdings", "international", "the", "air", "lines", "airlines"}


def company_terms(name: str | None, domain: str | None) -> list[str]:
    """Names a news headline may use for the company: the full name, the name without corporate
    words ("Marriott International" -> "Marriott"), the first word, and the domain label."""
    terms: list[str] = []
    if name:
        words = re.findall(r"[A-Za-z0-9&']+", name)
        terms.append(" ".join(words))
        core = [w for w in words if w.lower() not in _SUFFIX_WORDS]
        if core:
            terms.append(" ".join(core))
        if words and len(words[0]) >= 4:
            terms.append(words[0])
    if domain:
        label = domain.lower().removeprefix("www.").split(".")[0]
        if len(label) >= 4:
            terms.append(label)
    out: list[str] = []
    for t in terms:
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out


def headline(title: str) -> str:
    """Google News titles end with " - Outlet". The outlet is not part of the story."""
    return title.rsplit(" - ", 1)[0] if " - " in title else title


def mentions_company(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])", low) for t in terms)


_RETRY_WITH_WWW = {"network_error", "dns_failure", "timeout", "tls_error"}
_HREF_RE = re.compile(r"""<a\s[^>]*href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


class PublicWebProvider:
    """Reads the company site (home and about), Wikipedia (summary and page), and Google News."""

    def __init__(self, fetcher: Fetcher | None = None, max_doc_chars: int = MAX_DOC_CHARS,
                 sleep: Callable[[float], None] = time.sleep):
        self.fetcher = fetcher or Fetcher()
        self.max_doc_chars = max_doc_chars
        self._sleep = sleep

    # -- main entry ---------------------------------------------------------------------------
    def research(self, company_name: str | None, domain: str | None) -> RawResearch:
        """Wikipedia, the company site, and the news are fetched at the same time (no Bedrock
        here, so the 1 request per second limit is not involved). Results are merged in a fixed
        order, so the output does not depend on which fetch finished first."""
        domain = domain.lower() if domain else None
        wiki_part, site_part, news_part = RawResearch(), RawResearch(), RawResearch()
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="research") as pool:
            wiki_job = pool.submit(self._wikipedia, wiki_part, company_name, domain)
            site_job = pool.submit(self._website, site_part, domain)
            news_job = pool.submit(self._news, news_part, company_name, domain)
            wiki_confirmed, site_ok = wiki_job.result(), site_job.result()
            news_job.result()
        raw = RawResearch()
        for part in (wiki_part, site_part, news_part):
            raw.documents += part.documents
            raw.sources += part.sources
        raw.news = news_part.news
        wiki_found = any(d.kind in (KIND_WIKI_SUMMARY, KIND_WIKI_PAGE) for d in raw.documents)
        raw.match_confidence = (
            "confirmed" if wiki_confirmed or (not wiki_found and site_ok) else "unverified_match"
        )
        return raw

    def _get(self, raw: RawResearch, url: str) -> FetchResult:
        result = self.fetcher.fetch(url)
        # A rate limit answer (429) is polite to wait out, briefly and at most twice.
        for _ in range(MAX_RATE_LIMIT_RETRIES):
            if result.ok or result.error != "http_429":
                break
            self._sleep(min(result.retry_after or 1.0, MAX_RETRY_WAIT_S))
            result = self.fetcher.fetch(url)
        raw.sources.append(SourceStatus(url, "ok" if result.ok else "failed"))
        return result

    # -- Wikipedia (R3.1, R3.15) ----------------------------------------------------------------
    def _wikipedia(self, raw: RawResearch, name: str | None, domain: str | None) -> bool:
        if not name:
            raw.sources.append(SourceStatus("skipped:no-company-name:wikipedia", "skipped"))
            return False
        search = self._get(raw, f"{WIKI_API}/w/rest.php/v1/search/page?q={quote(name)}&limit=5")
        if not search.ok:
            return False
        try:
            pages = json.loads(search.body).get("pages", [])
        except (ValueError, AttributeError):
            return False
        candidates = [p for p in pages if isinstance(p, dict) and p.get("key") and _names_overlap(name, p.get("title", ""))][:3]
        chosen: dict[str, Any] | None = None
        chosen_html = ""
        confirmed = False
        for cand in candidates[:2]:  # at most two page fetches
            page = self._get(raw, f"{WIKI_API}/api/rest_v1/page/html/{quote(cand['key'], safe='')}")
            if not page.ok:
                continue
            if chosen is None:
                chosen, chosen_html = cand, page.text
            if domain and domain in page.body.lower():
                chosen, chosen_html, confirmed = cand, page.text, True
                break
        if chosen is None:
            return False

        wiki_url = f"{WIKI_API}/wiki/{quote(chosen['key'], safe='()_')}"
        summary = self._get(raw, f"{WIKI_API}/api/rest_v1/page/summary/{quote(chosen['key'], safe='')}")
        if summary.ok:
            try:
                extract = (json.loads(summary.body).get("extract") or "").strip()
            except (ValueError, AttributeError):
                extract = ""
            if extract:
                raw.documents.append(SourceDoc(wiki_url, KIND_WIKI_SUMMARY, _trim(extract, self.max_doc_chars), chosen.get("title")))
        if chosen_html:
            raw.documents.append(SourceDoc(wiki_url, KIND_WIKI_PAGE, _trim(chosen_html, MAX_WIKI_PAGE_CHARS), chosen.get("title")))
        if raw.documents:
            raw.sources.append(SourceStatus(wiki_url, "ok"))  # the citable page URL
        return confirmed

    # -- company website ---------------------------------------------------------------------------
    def _website(self, raw: RawResearch, domain: str | None) -> bool:
        if not domain:
            raw.sources.append(SourceStatus("skipped:no-domain:website", "skipped"))
            return False
        home = self._get(raw, f"https://{domain}/")
        if not home.ok and home.error in _RETRY_WITH_WWW and not domain.startswith("www."):
            # Some sites only answer on the www host. A 403 is not retried: that is a block.
            home = self._get(raw, f"https://www.{domain}/")
        if not home.ok:
            return False
        raw.documents.append(SourceDoc(home.final_url, KIND_HOMEPAGE, _trim(home.text, self.max_doc_chars)))
        raw.sources.append(SourceStatus(home.final_url, "ok"))
        about_url = self._find_about_link(home, domain)
        if about_url:
            about = self._get(raw, about_url)
            if about.ok:
                raw.documents.append(SourceDoc(about.final_url, KIND_ABOUT, _trim(about.text, self.max_doc_chars)))
                raw.sources.append(SourceStatus(about.final_url, "ok"))
        return True

    @staticmethod
    def _find_about_link(home: FetchResult, domain: str) -> str | None:
        for href in _HREF_RE.findall(home.body):
            if "about" not in href.lower() or href.startswith(("#", "mailto:", "javascript:")):
                continue
            absolute = urljoin(home.final_url, href).split("#")[0]
            if urlsplit(absolute).scheme in ("http", "https") and _same_site(absolute, domain) and absolute != home.final_url:
                return absolute
        return None

    # -- Google News RSS (R3.9) -----------------------------------------------------------------------
    def _news(self, raw: RawResearch, name: str | None, domain: str | None) -> None:
        query = name or domain
        if not query:
            raw.sources.append(SourceStatus("skipped:no-company:news", "skipped"))
            return
        feed = self._get(raw, NEWS_RSS.format(q=quote(query)))
        if not feed.ok:
            return
        try:
            root = SafeET.fromstring(feed.body.encode("utf-8"))
        except Exception:  # malformed or hostile XML
            return
        terms = company_terms(name, domain)
        items: list[NewsItem] = []
        seen_titles: set[str] = set()
        seen_urls: set[str] = set()
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or urlsplit(link).scheme not in ("http", "https"):
                continue
            if not mentions_company(headline(title), terms):
                continue  # an article that does not name the company is not news about it
            key = _key(headline(title))
            if key in seen_titles or link in seen_urls:
                continue  # the same story from a second feed entry
            seen_titles.add(key)
            seen_urls.add(link)
            items.append(NewsItem(title, _rss_date(item.findtext("pubDate")), link))
        items.sort(key=lambda n: n.date or "", reverse=True)
        raw.news = items[: c.MAX_NEWS_ITEMS]
        for n in raw.news:
            raw.documents.append(SourceDoc(n.url, KIND_NEWS, n.title, n.title))
            raw.sources.append(SourceStatus(n.url, "ok"))


class FixtureProvider:
    """Replays recorded research. A missing fixture behaves like every source having failed."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    @staticmethod
    def fixture_key(company_name: str | None, domain: str | None) -> str:
        return (domain or _key(company_name or "unknown")).lower()

    def research(self, company_name: str | None, domain: str | None) -> RawResearch:
        path = self.root / f"{self.fixture_key(company_name, domain)}.json"
        if not path.exists():
            return RawResearch(sources=[SourceStatus(f"missing-fixture:{path.name}", "failed")])
        return RawResearch.from_dict(json.loads(path.read_text(encoding="utf-8")))
