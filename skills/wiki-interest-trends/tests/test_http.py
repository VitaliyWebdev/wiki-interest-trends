import pytest
import requests

from wikitrends.errors import AppError
from wikitrends.http import HttpResult, build_session, get_json

from fakes import FakeResponse, FakeSession


@pytest.fixture
def recorded_sleeps():
    delays = []
    return delays, delays.append


def test_get_json_returns_data_on_200(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(200, {"views": 42})])

    result = get_json(session, "https://example.org/a", sleep=sleep)

    assert result == HttpResult(200, {"views": 42})
    assert session.calls == ["https://example.org/a"]
    assert delays == []


def test_get_json_returns_404_immediately_without_retry(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(404, {"status": 404, "title": "Not Found"})])

    result = get_json(session, "https://example.org/missing", sleep=sleep)

    assert result == HttpResult(404, {"status": 404, "title": "Not Found"})
    assert len(session.calls) == 1
    assert delays == []


def test_get_json_handles_404_with_non_json_body(recorded_sleeps):
    _, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(404, json_raises=True)])

    result = get_json(session, "https://example.org/missing", sleep=sleep)

    assert result == HttpResult(404, None)


def test_get_json_retries_on_500_then_succeeds(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(500), FakeResponse(200, {"ok": True})])

    result = get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.5)

    assert result == HttpResult(200, {"ok": True})
    assert len(session.calls) == 2
    assert delays == [0.5]


def test_get_json_retries_on_429_then_succeeds(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(429), FakeResponse(200, {"ok": True})])

    result = get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.5)

    assert result == HttpResult(200, {"ok": True})
    assert delays == [0.5]


def test_get_json_uses_exponential_backoff_across_retries(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(200, {})])

    get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.5)

    assert delays == [0.5, 1.0]


def test_get_json_gives_up_after_max_retries(recorded_sleeps):
    _, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(500)] * 4)

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.01, max_retries=3)

    assert exc_info.value.error_code == "upstream_unavailable"
    assert len(session.calls) == 4


def test_get_json_raises_immediately_on_other_4xx(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession([FakeResponse(400, {"detail": "bad request"})])

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://example.org/a", sleep=sleep)

    assert exc_info.value.error_code == "http_error"
    assert len(session.calls) == 1
    assert delays == []


def test_get_json_retries_on_network_exception_then_succeeds(recorded_sleeps):
    delays, sleep = recorded_sleeps
    session = FakeSession(
        [requests.exceptions.ConnectionError("boom"), FakeResponse(200, {"ok": True})]
    )

    result = get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.5)

    assert result == HttpResult(200, {"ok": True})
    assert delays == [0.5]


def test_get_json_gives_up_after_persistent_network_exception(recorded_sleeps):
    _, sleep = recorded_sleeps
    session = FakeSession([requests.exceptions.ConnectionError("boom")] * 4)

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://example.org/a", sleep=sleep, backoff_base=0.01, max_retries=3)

    assert exc_info.value.error_code == "network_error"


def test_network_error_hint_tells_the_agent_to_verify_before_blaming_the_network():
    # Real incident: an agent session confidently told a user "your
    # organization's network policy blocks this" when the actual cause was
    # that specific process, not the user's real network -- verified false
    # by the user running curl themselves. The hint must steer future
    # agents to check first, not repeat that mistake.
    session = FakeSession([requests.exceptions.ConnectionError("boom")])

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://example.org/a", sleep=lambda s: None, max_retries=0)

    hint = exc_info.value.hint
    assert "curl" in hint
    assert "verify" in hint.lower()


def test_network_error_hint_curls_the_exact_url_that_failed():
    # This skill talks to three different host patterns (www.wikidata.org,
    # wikimedia.org, and a per-language *.wikipedia.org host). A hint that
    # always tests the same hardcoded host gives a false "all clear" when
    # the host that actually failed was a different one -- the agent then
    # wrongly rules out a real, host-specific block. The curl command must
    # target the URL that actually failed, not a fixed stand-in.
    session = FakeSession([requests.exceptions.ConnectionError("boom")])
    failing_url = "https://pl.wikipedia.org/w/api.php?action=query&redirects"

    with pytest.raises(AppError) as exc_info:
        get_json(session, failing_url, sleep=lambda s: None, max_retries=0)

    hint = exc_info.value.hint
    assert f"curl -sv '{failing_url}'" in hint


def test_network_error_hint_mentions_sandbox_host_approval():
    # A silent, deterministic sandbox host-allowlist block (Claude Code's
    # Bash sandbox pre-allows no domains, and this skill touches multiple
    # hosts) looks identical to a transient network error from inside this
    # script -- the difference only shows up in the Bash tool's own result.
    # The hint must point the agent at that distinction, not just at curl.
    session = FakeSession([requests.exceptions.ConnectionError("boom")])

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://wikimedia.org/api/rest_v1/x", sleep=lambda s: None, max_retries=0)

    hint = exc_info.value.hint.lower()
    assert "sandbox" in hint
    assert "blocked host" in hint or "disallowed" in hint


def test_network_error_hint_mentions_claude_ai_capabilities_network_egress():
    # Real incident, a third and distinct one: claude.ai chat / Claude
    # Desktop have no local Bash tool at all, so the Claude-Code-specific
    # "check the Bash tool's own result" advice doesn't apply -- yet an
    # agent there hit this same error and still (wrongly) told the user
    # it was their organization's network. In that product, the actual
    # switch is claude.ai's own Capabilities > Code execution > Allow
    # network egress setting (or the org admin's equivalent), which is
    # nothing IT can act on. The hint must name that specific setting,
    # not just generically say "ask your admin".
    session = FakeSession([requests.exceptions.ConnectionError("boom")])

    with pytest.raises(AppError) as exc_info:
        get_json(session, "https://uk.wikipedia.org/w/api.php?action=query", sleep=lambda s: None, max_retries=0)

    hint = exc_info.value.hint
    assert "Capabilities" in hint
    assert "network egress" in hint.lower()
    assert "claude.ai" in hint.lower() or "claude desktop" in hint.lower()


def test_build_session_sets_user_agent_with_given_contact():
    session = build_session(contact="me@example.org")

    assert "me@example.org" in session.headers["User-Agent"]
    assert "wiki-interest-trends" in session.headers["User-Agent"]


def test_build_session_uses_default_contact_when_none_given():
    session = build_session(contact=None)

    assert "wiki-interest-trends" in session.headers["User-Agent"]
    assert session.headers["User-Agent"]
