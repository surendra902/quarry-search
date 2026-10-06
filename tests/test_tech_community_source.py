"""Regression tests at the public adapter boundary; never use the network."""
from unittest.mock import Mock, patch

from quarry.sources.tech_community_source import TechCommunitySource

LINK = "https://claude.ai/referral/Native42Ab"
DEV_URL = "https://dev.to/alice/native-article"
QIITA_URL = "https://qiita.com/bob/items/0123456789abcdef0123"


def response(data, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = data
    return result


def test_dev_fetches_native_detail_body_not_unsupported_list_search():
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.startswith("https://qiita.com/"):
            return response([])
        if url == "https://dev.to/api/articles/123":
            return response({"id": 123, "url": DEV_URL, "body_markdown": f"[pass]({LINK})",
                             "published_at": "2026-09-01T01:02:03Z", "user": {"username": "alice"}})
        return response([{"id": 123, "url": DEV_URL, "description": "No link in preview"}])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        records = source.discover_new()
    assert len(records) == 1
    assert records[0].url == LINK
    assert records[0].source_url == DEV_URL
    assert records[0].evidence_kind == "direct_match"
    assert LINK in records[0].evidence_snippet
    assert records[0].author == "alice"
    assert records[0].timestamp_basis == "devto_published_at"
    assert any(url == "https://dev.to/api/articles/123" for url, _ in calls)
    listing = next(kwargs for url, kwargs in calls if url == "https://dev.to/api/articles")
    assert listing["params"]["tag"] == "claude"
    assert all("q=" not in url and "q" not in kwargs.get("params", {}) for url, kwargs in calls)


def test_native_html_href_and_same_code_on_multiple_articles_are_retained():
    def get(url, **kwargs):
        if url == "https://dev.to/api/articles":
            return response([{"id": 123}, {"id": 124}])
        if url.startswith("https://dev.to/api/articles/"):
            return response({"url": DEV_URL + url.rsplit("/", 1)[-1],
                             "body_html": f'<a href="{LINK}">claim</a>', "user": None})
        assert kwargs["params"]["query"] == '"claude.ai/referral"'
        assert "?" not in url
        return response([{"url": QIITA_URL, "body": f"[pass]({LINK})", "user": {},
                          "created_at": "2026-09-02T12:00:00+09:00",
                          "updated_at": "2026-09-03T12:00:00+09:00"}])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        records = source.discover_new()
    assert len(records) == 3
    assert len({r.source_url for r in records}) == 3
    assert all(r.referral_code == "Native42Ab" and LINK in r.evidence_snippet for r in records)
    assert all(r.author is None for r in records)
    assert records[0].published_at is None and records[0].timestamp_basis is None
    assert records[-1].timestamp_basis == "qiita_created_at"
    assert records[-1].published_at == "2026-09-02T12:00:00+09:00"
    assert records[-1].source_updated_at == "2026-09-03T12:00:00+09:00"
    assert source.last_report["request_count"] == 4


def test_find_sources_requires_full_url_and_exact_token_in_native_content():
    def get(url, **kwargs):
        if url.startswith("https://dev.to/"):
            return response([])
        assert kwargs["params"]["query"] == f'"{LINK}"'
        return response([
            {"url": QIITA_URL + "/mention", "body": "Native42Ab"},
            {"url": QIITA_URL + "/schemeless", "body": "claude.ai/referral/Native42Ab"},
            {"url": QIITA_URL + "/wrong", "body": LINK + "Extra"},
            {"url": QIITA_URL + "/host", "body": "https://claude.ai.evil/referral/Native42Ab"},
            {"url": QIITA_URL, "rendered_body": f'<a href="{LINK}">pass</a>'},
        ])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        records = source.find_sources("Native42Ab")
    assert len(records) == 1
    assert records[0].source_url == QIITA_URL
    assert records[0].evidence_kind == "direct_match"
    assert LINK in records[0].evidence_snippet


def test_non_200_is_not_a_healthy_empty_result():
    for status, expected in [(429, "rate_limited"), (403, "blocked"), (500, "error")]:
        source = TechCommunitySource()
        with patch("requests.get", return_value=response({}, status)):
            assert source.discover_new() == []
        assert source.last_report["status"] == expected
        assert source.last_report["request_count"] == 2
        assert any(f"HTTP {status}" in message for message in source.last_report["messages"])


def test_detail_failure_does_not_promote_list_preview_to_evidence():
    def get(url, **kwargs):
        if url == "https://dev.to/api/articles":
            return response([{"id": 123, "url": DEV_URL, "description": LINK}])
        if url == "https://dev.to/api/articles/123":
            return response({}, 429)
        return response([])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        assert source.discover_new() == []
    assert source.last_report["status"] == "partial"
    assert any("HTTP 429" in message for message in source.last_report["messages"])


def test_latest_fallback_and_request_budget_leave_qiita_coverage():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url == "https://dev.to/api/articles":
            return response([])
        if url == "https://dev.to/api/articles/latest":
            assert kwargs["params"] == {"page": 1, "per_page": 30}
            return response([{"id": number} for number in range(1, 31)])
        if url.startswith("https://dev.to/"):
            return response({"url": DEV_URL, "body_markdown": LINK})
        return response([{"url": QIITA_URL, "body": LINK}])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        records = source.discover_new()
    assert len(records) == 2
    assert len(calls) == source.max_requests == 4
    assert calls[-1] == "https://qiita.com/api/v2/items"
    assert source.last_report["status"] == "partial"
    assert any("not a full-text" in message for message in source.last_report["messages"])


def test_time_budget_prevents_network_and_is_reported():
    source = TechCommunitySource()
    source.budget_seconds = 0
    with patch("requests.get") as get:
        assert source.discover_new() == []
    get.assert_not_called()
    assert source.last_report["status"] == "partial"
    assert source.last_report["request_count"] == 0


def test_malformed_json_and_network_failure_are_visible():
    import requests

    for failure in [ValueError("bad json"), requests.Timeout("timeout")]:
        source = TechCommunitySource()
        with patch("requests.get", side_effect=failure):
            assert source.discover_new() == []
        assert source.last_report["status"] == "error"
    source = TechCommunitySource()
    with patch("requests.get", return_value=response({"unexpected": "object"})):
        assert source.discover_new() == []
    assert source.last_report["status"] == "error"


def test_result_limit_zero_invalid_token_and_missing_native_body():
    source = TechCommunitySource()
    with patch("requests.get") as get:
        assert source.discover_new(0) == []
        assert source.find_sources("not a token") == []
    get.assert_not_called()
    assert source.last_report["status"] == "error"

    def get(url, **kwargs):
        if url.startswith("https://dev.to/"):
            return response([])
        return response([{"url": QIITA_URL, "title": LINK}])

    with patch("requests.get", side_effect=get):
        assert source.discover_new() == []
    assert source.last_report["status"] == "partial"
    assert any("missing native body" in message for message in source.last_report["messages"])


def test_result_limit_reports_omitted_occurrences_and_report_resets():
    source = TechCommunitySource()

    def get(url, **kwargs):
        if url == "https://dev.to/api/articles":
            return response([{"id": 123}])
        if url.startswith("https://dev.to/"):
            return response({"url": DEV_URL, "body_markdown": LINK, "published_at": "not-a-date"})
        return response([{"url": QIITA_URL, "body": LINK}])

    with patch("requests.get", side_effect=get):
        records = source.discover_new(limit=1)
    assert len(records) == 1
    assert records[0].published_at is None
    assert records[0].timestamp_basis is None
    assert source.last_report["status"] == "partial"
    assert any("Result limit" in message for message in source.last_report["messages"])
    with patch("requests.get", return_value=response([])):
        assert source.discover_new() == []
    assert source.last_report["status"] == "ok"
    assert not any("Result limit" in message for message in source.last_report["messages"])


def test_qiita_malformed_item_does_not_hide_later_native_proof():
    def get(url, **kwargs):
        if url.startswith("https://dev.to/"):
            return response([])
        return response([None, {"url": QIITA_URL, "body": LINK}])

    source = TechCommunitySource()
    with patch("requests.get", side_effect=get):
        records = source.discover_new()
    assert len(records) == 1
    assert source.last_report["status"] == "partial"
