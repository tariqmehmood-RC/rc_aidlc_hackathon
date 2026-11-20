"""Safe fetching of public web pages for company research (requirements R3.16, R3.17).

Rules:
- only http and https, on ports 80 and 443, no user info in the URL;
- the host is resolved first and every address must be a public one (no private, loopback,
  link-local, or reserved ranges), also after each redirect;
- the connection goes to the address that was checked (no second DNS lookup);
- timeout, size cap, and redirect limit; no compressed bodies;
- an honest User-Agent. A site that answers 403 gives a failed result: we do not try to get
  around bot protection.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit

USER_AGENT = "InsideSalesCopilot/0.1 (hackathon research tool; contact: team-5)"
DEFAULT_TIMEOUT_S = 8.0
MAX_BYTES = 500_000
MAX_REDIRECTS = 3
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/json",
              "application/xml", "text/xml", "application/rss+xml", "application/atom+xml")

Resolver = Callable[[str, int], list[str]]
Connector = Callable[[str, int, float], socket.socket]


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    ok: bool
    status: int | None = None
    text: str = ""          # HTML turned into plain text. Other types are returned as they are.
    body: str = ""          # decoded body as received (up to the size cap)
    content_type: str | None = None
    truncated: bool = False
    error: str | None = None
    retry_after: float | None = None  # seconds, from a Retry-After header on 429 and 503


def is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    seen: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in seen:
            seen.append(addr)
    return seen


def default_connector(ip: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((ip, port), timeout=timeout)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, ip, connector, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip, self._connector = ip, connector

    def connect(self):
        self.sock = self._connector(self._ip, self.port, self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, connector, timeout):
        self._tls = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._tls)
        self._ip, self._connector = ip, connector

    def connect(self):
        raw = self._connector(self._ip, self.port, self.timeout)
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)


# --- HTML to text ---------------------------------------------------------------------------
_SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "head", "iframe"}
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header",
               "footer", "nav", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "main"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Remove tags, scripts, and styles. Returns plain text with single spaces."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # broken markup must not break research
        pass
    return " ".join("".join(parser.parts).split())


def _decode(data: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type and "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[1].split(";")[0].strip(" \"'") or "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(
        self,
        resolver: Resolver = default_resolver,
        connector: Connector = default_connector,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = MAX_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        allowed_ports: tuple[int, ...] = (80, 443),
        user_agent: str = USER_AGENT,
    ):
        self._resolver = resolver
        self._connector = connector
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.allowed_ports = allowed_ports
        # RESEARCH_USER_AGENT lets a deployment set a User-Agent with a real contact address,
        # as Wikimedia asks. Never put secrets in it.
        self.user_agent = os.environ.get("RESEARCH_USER_AGENT") or user_agent

    def fetch(self, url: str) -> FetchResult:
        current = url
        for _hop in range(self.max_redirects + 1):
            outcome = self._get_once(url, current)
            if isinstance(outcome, FetchResult):
                return outcome
            current = outcome  # a redirect target
        return FetchResult(url, current, ok=False, error="too_many_redirects")

    # -- one request. Returns a FetchResult, or the next URL when the server redirects. --------
    def _get_once(self, original: str, url: str) -> FetchResult | str:
        def fail(error: str, status: int | None = None) -> FetchResult:
            return FetchResult(original, url, ok=False, status=status, error=error)

        try:
            parts = urlsplit(url)
            host = parts.hostname
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return fail("bad_url")
        if parts.scheme not in ("http", "https"):
            return fail("bad_scheme")
        if not host or parts.username or parts.password:
            return fail("bad_url")

        try:
            addresses = self._resolver(host, port)
        except (OSError, UnicodeError):
            return fail("dns_failure")
        if not addresses:
            return fail("dns_failure")
        if not all(is_public_ip(a) for a in addresses):
            return fail("blocked_address")
        if port not in self.allowed_ports:
            return fail("bad_port")

        conn_cls = _PinnedHTTPSConnection if parts.scheme == "https" else _PinnedHTTPConnection
        conn = conn_cls(host, port, addresses[0], self._connector, self.timeout)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:
            conn.request("GET", path, headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "identity",
            })
            resp = conn.getresponse()
            status = resp.status
            if status in (301, 302, 303, 307, 308):
                location = resp.getheader("Location")
                if not location:
                    return fail("bad_redirect", status)
                return urljoin(url, location)
            if status < 200 or status >= 300:
                failed = fail(f"http_{status}", status)
                retry_after = resp.getheader("Retry-After")
                if status in (429, 503) and retry_after and retry_after.strip().isdigit():
                    return FetchResult(failed.url, failed.final_url, ok=False, status=status,
                                       error=failed.error, retry_after=float(retry_after))
                return failed
            content_type = resp.getheader("Content-Type")
            media = (content_type or "").split(";")[0].strip().lower()
            if media and not media.startswith(TEXT_TYPES) and media not in TEXT_TYPES:
                return fail("unsupported_content_type", status)
            data = resp.read(self.max_bytes + 1)
            truncated = len(data) > self.max_bytes
            if truncated:
                data = data[: self.max_bytes]
            body = _decode(data, content_type)
            text = html_to_text(body) if media in ("text/html", "application/xhtml+xml", "") else body
            return FetchResult(original, url, ok=True, status=status, text=text, body=body,
                               content_type=content_type, truncated=truncated)
        except (socket.timeout, TimeoutError):
            return fail("timeout")
        except ssl.SSLError:
            return fail("tls_error")
        except (OSError, http.client.HTTPException):
            return fail("network_error")
        finally:
            conn.close()
