# Tests for scrape_pipeline.py. The Firecrawl API is replaced with a fake
# (no network calls, no API credits used).
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scrape_pipeline as sp  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


def ok_payload(n=5):
    return {"success": True, "data": {"web": [
        {"title": f"Page {i}", "url": f"https://ir.chipotle.com/page-{i}", "markdown": f"# Page {i}"}
        for i in range(1, n + 1)
    ]}}


def fake_post(responses):
    # Returns each queued response in turn; an Exception in the queue is raised
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(timeout)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    post.calls = calls
    return post


def no_sleep(seconds):
    pass


# --- file naming and content -------------------------------------------------

def test_slug_matches_existing_file_names():
    assert sp.slugify_url("https://ir.chipotle.com/news-releases") == "ir-chipotle-com-news-releases"


def test_save_result_writes_frontmatter_and_body(tmp_path):
    r = {"title": "News Releases", "url": "https://ir.chipotle.com/news-releases", "markdown": "# News"}
    path = sp.save_result(r, tmp_path, "2026-09-30", 1)
    assert path.name == "01-2026-09-30-ir-chipotle-com-news-releases.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: News Releases\nurl: https://ir.chipotle.com/news-releases\nscraped: 2026-09-30\n---\n\n")
    assert text.endswith("# News")


def test_save_result_handles_missing_markdown(tmp_path):
    # Design spec: a page that failed to scrape still gets a file, with an empty body
    r = {"title": "Empty", "url": "https://ir.chipotle.com/x", "markdown": None}
    text = sp.save_result(r, tmp_path, "2026-09-30", 2).read_text(encoding="utf-8")
    assert text.endswith("---\n\n")


# --- search: success, retries, and clear failures -----------------------------

def test_search_returns_results_and_sets_a_timeout():
    post = fake_post([FakeResponse(200, ok_payload())])
    results = sp.search("key", post=post, sleep=no_sleep)
    assert len(results) == 5
    assert post.calls[0] is not None  # never wait forever on a hung request


def test_search_retries_after_network_error_then_succeeds():
    post = fake_post([requests.ConnectionError("blip"), FakeResponse(200, ok_payload())])
    assert len(sp.search("key", post=post, sleep=no_sleep)) == 5


def test_search_retries_on_rate_limit_and_server_errors():
    post = fake_post([FakeResponse(429, {}), FakeResponse(503, {}), FakeResponse(200, ok_payload())])
    assert len(sp.search("key", post=post, sleep=no_sleep)) == 5


def test_search_gives_up_after_three_attempts():
    post = fake_post([FakeResponse(500, {})] * 3)
    with pytest.raises(sp.ScrapeError, match="3 attempts"):
        sp.search("key", post=post, sleep=no_sleep)


def test_search_does_not_retry_a_bad_api_key():
    post = fake_post([FakeResponse(401, {"error": "Unauthorized"})])
    with pytest.raises(sp.ScrapeError, match="401"):
        sp.search("key", post=post, sleep=no_sleep)
    assert len(post.calls) == 1


def test_search_rejects_an_unexpected_response_shape():
    post = fake_post([FakeResponse(200, {"success": True, "data": {}})])
    with pytest.raises(sp.ScrapeError, match="unexpected"):
        sp.search("key", post=post, sleep=no_sleep)


# --- a full run ----------------------------------------------------------------

def test_run_saves_every_result(tmp_path):
    post = fake_post([FakeResponse(200, ok_payload(5))])
    saved = sp.run("key", tmp_path, "2026-09-30", post=post, sleep=no_sleep)
    assert len(saved) == 5
    assert len(list(tmp_path.glob("*.md"))) == 5


def test_run_fails_loudly_when_nothing_comes_back(tmp_path):
    # An empty week should fail the workflow (GitHub emails), not pass silently
    post = fake_post([FakeResponse(200, ok_payload(0))])
    with pytest.raises(sp.ScrapeError, match="no results"):
        sp.run("key", tmp_path, "2026-09-30", post=post, sleep=no_sleep)


def test_main_exits_with_a_clear_message_when_the_key_is_missing(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(sp, "load_dotenv", lambda: None)
    with pytest.raises(SystemExit, match="FIRECRAWL_API_KEY"):
        sp.main()


def test_importing_the_module_does_not_call_the_api(monkeypatch):
    # The scrape must only run from main(), so tests and imports are safe
    import importlib

    def boom(*a, **k):
        raise AssertionError("API called on import")

    monkeypatch.setattr(requests, "post", boom)
    importlib.reload(sp)
