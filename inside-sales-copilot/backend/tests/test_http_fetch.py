import http.server
import ipaddress
import socket
import threading
import time

import pytest

from backend.src.lib import http_fetch as hf

PUBLIC_IP = "93.184.216.34"
HTML = """<html><head><title>T</title><style>body{color:red}</style></head>
<body><script>var secret = 'x';</script><h1>Hello &amp; welcome</h1><p>First   paragraph.</p>
<noscript>enable js</noscript><div>Second<br>line</div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status, body=b"", ctype="text/html; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path
        self.server.seen_headers.append(dict(self.headers))
        if path == "/ok":
            self._send(200, HTML.encode())
        elif path == "/big":
            self._send(200, b"a" * 700_000, ctype="text/plain")
        elif path == "/slow":
            time.sleep(1.0)
            self._send(200, b"late")
        elif path == "/forbidden":
            self._send(403, b"<html>Cloudflare</html>")
        elif path == "/limited":
            self._send(429, b"slow down", headers={"Retry-After": "7"})
        elif path == "/to-private":
            self._send(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        elif path == "/to-ok":
            self._send(302, headers={"Location": "/ok"})
        elif path == "/loop":
            self._send(302, headers={"Location": "/loop"})
        elif path == "/json":
            self._send(200, b'{"a": 1}', ctype="application/json")
        elif path == "/image":
            self._send(200, b"\x89PNG", ctype="image/png")
        elif path == "/latin1":
            self._send(200, "caf\xe9".encode("latin-1"), ctype="text/plain; charset=latin-1")
        else:
            self._send(404, b"nope")


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.seen_headers = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def fake_resolver(host, port):
    """Like getaddrinfo: an IP literal resolves to itself, a name resolves to a public address."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        return [PUBLIC_IP]


@pytest.fixture()
def fetcher(server):
    port = server.server_address[1]

    def connector(ip, p, timeout):
        # the test server is on localhost, so any checked address is sent there
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    return hf.Fetcher(resolver=fake_resolver, connector=connector, allowed_ports=(port,), timeout=0.4), port


def url(port, path):
    return f"http://example.test:{port}{path}"


# --- success -------------------------------------------------------------------------------
def test_fetches_a_page_and_strips_html(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/ok"))
    assert result.ok and result.status == 200
    assert "Hello & welcome" in result.text
    assert "First paragraph." in result.text
    assert "var secret" not in result.text and "color:red" not in result.text
    assert "enable js" not in result.text
    assert "<" not in result.text
    assert "<script>" in result.body  # the raw body is kept for link extraction


def test_sends_an_honest_user_agent_and_no_compression(fetcher, server):
    f, port = fetcher
    f.fetch(url(port, "/ok"))
    headers = server.seen_headers[-1]
    assert headers["User-Agent"] == hf.USER_AGENT and "InsideSalesCopilot" in headers["User-Agent"]
    assert headers["Accept-Encoding"] == "identity"


def test_redirect_to_a_normal_page_is_followed(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/to-ok"))
    assert result.ok and result.final_url.endswith("/ok") and result.url.endswith("/to-ok")


def test_json_is_returned_unchanged(fetcher):
    f, port = fetcher
    assert f.fetch(url(port, "/json")).text == '{"a": 1}'


def test_charset_is_respected(fetcher):
    f, port = fetcher
    assert f.fetch(url(port, "/latin1")).text == "caf\xe9"


# --- limits and failures -------------------------------------------------------------------
def test_oversized_body_is_cut_off(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/big"))
    assert result.ok and result.truncated
    assert len(result.body) == hf.MAX_BYTES


def test_slow_server_gives_a_timeout_failure(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/slow"))
    assert not result.ok and result.error == "timeout"


def test_403_is_a_failure_not_an_exception(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/forbidden"))
    assert not result.ok and result.status == 403 and result.error == "http_403"


def test_404_is_a_failure(fetcher):
    f, port = fetcher
    assert fetcher[0].fetch(url(port, "/missing")).error == "http_404"


def test_redirect_loop_stops_after_three_redirects(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/loop"))
    assert not result.ok and result.error == "too_many_redirects"


def test_non_text_content_is_refused(fetcher):
    f, port = fetcher
    assert f.fetch(url(port, "/image")).error == "unsupported_content_type"


# --- blocked targets -----------------------------------------------------------------------
@pytest.mark.parametrize("bad_url", [
    "file:///etc/passwd",
    "ftp://example.com/file",
    "gopher://example.com/",
    "javascript:alert(1)",
    "//example.com/path",
    "not a url",
    "",
])
def test_other_schemes_and_malformed_urls_are_refused(bad_url):
    result = hf.Fetcher().fetch(bad_url)
    assert not result.ok and result.error in {"bad_scheme", "bad_url", "dns_failure"}


@pytest.mark.parametrize("private_url", [
    "http://127.0.0.1/",
    "http://127.0.0.1:8080/",
    "http://10.0.0.5/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[fd00::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://100.64.0.1/",
    "http://0.0.0.0/",
    "https://localhost/",
])
def test_private_loopback_and_link_local_addresses_are_refused(private_url):
    calls = []
    f = hf.Fetcher(connector=lambda *a: calls.append(a))
    result = f.fetch(private_url)
    assert not result.ok and result.error == "blocked_address"
    assert calls == []  # no connection was even attempted


def test_a_name_that_resolves_to_a_private_address_is_refused():
    calls = []
    f = hf.Fetcher(resolver=lambda h, p: ["10.1.2.3"], connector=lambda *a: calls.append(a))
    result = f.fetch("http://internal.example.com/")
    assert result.error == "blocked_address" and calls == []


def test_one_private_address_among_several_blocks_the_fetch():
    f = hf.Fetcher(resolver=lambda h, p: [PUBLIC_IP, "10.0.0.1"], connector=lambda *a: None)
    assert f.fetch("http://mixed.example.com/").error == "blocked_address"


def test_redirect_to_a_private_address_is_refused(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/to-private"))
    assert not result.ok and result.error == "blocked_address"
    assert "169.254.169.254" in result.final_url


def test_unusual_ports_and_user_info_are_refused():
    f = hf.Fetcher(resolver=fake_resolver, connector=lambda *a: None)
    assert f.fetch("http://example.com:8080/").error == "bad_port"
    assert f.fetch("http://user:pass@example.com/").error == "bad_url"


def test_dns_failure_is_reported():
    def boom(host, port):
        raise socket.gaierror("no such host")

    assert hf.Fetcher(resolver=boom).fetch("http://nope.example.com/").error == "dns_failure"


def test_is_public_ip():
    assert hf.is_public_ip("8.8.8.8") and hf.is_public_ip(PUBLIC_IP)
    assert not any(hf.is_public_ip(a) for a in ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "224.0.0.1", "garbage"])


# --- html_to_text on its own ---------------------------------------------------------------
def test_html_to_text_handles_broken_markup():
    assert hf.html_to_text("<p>One<p>Two <b>bold</b></i></div>") == "One Two bold"
    assert hf.html_to_text("") == ""


def test_html_to_text_drops_scripts_even_when_unclosed_tags_follow():
    assert "x=1" not in hf.html_to_text("<script>x=1</script><p>kept</p>")


def test_retry_after_header_is_reported_on_429(fetcher):
    f, port = fetcher
    result = f.fetch(url(port, "/limited"))
    assert not result.ok and result.error == "http_429" and result.retry_after == 7.0


def test_user_agent_can_be_overridden_from_the_environment(monkeypatch):
    monkeypatch.setenv("RESEARCH_USER_AGENT", "TeamBot/1.0 (+https://example.org/contact)")
    assert hf.Fetcher().user_agent == "TeamBot/1.0 (+https://example.org/contact)"
    monkeypatch.delenv("RESEARCH_USER_AGENT")
    assert hf.Fetcher().user_agent == hf.USER_AGENT
