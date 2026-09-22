# http.py — retrying JSON GET

**File:** `scripts/wikitrends/http.py`
**Tests:** `tests/test_http.py` (fake transport, no network)

## What it's for

The one place that talks HTTP for the whole skill. Every other module
(`wikidata.py`, and `pageviews.py` from Stage 3 on) calls `get_json()`
instead of using `requests` directly, so retry/backoff/error handling only
has to be correct once.

## Contract

```python
build_session(contact: str | None) -> requests.Session
get_json(session, url, *, max_retries=5, backoff_base=0.5, sleep=time.sleep) -> HttpResult
```

`HttpResult(status_code, data)` — `data` is the parsed JSON body, or `None`
if the body wasn't valid JSON (happens on some Wikimedia edge error pages,
which return HTML, not JSON).

Status handling, deliberately different per bucket:

| Status | Behavior |
|---|---|
| 200 | returned immediately as `HttpResult(200, json)` |
| 404 | returned immediately as `HttpResult(404, json_or_none)` — **no retry**. For Wikimedia pageviews this means "no data for this article/date range", not a failure; callers decide what it means for them. |
| 429, 5xx | retried with exponential backoff (`backoff_base * 2**attempt`), up to `max_retries`; raises `AppError(error_code="upstream_unavailable")` if still failing after that |
| network exception (`requests.exceptions.RequestException`) | same retry/backoff as 429/5xx, raises `AppError(error_code="network_error")` if it never recovers |
| any other 4xx | raises `AppError(error_code="http_error")` immediately, no retry — this is almost always a bug in how we built the URL, not a transient condition |

`sleep` is an injected callable (defaults to `time.sleep`) specifically so
tests can assert on backoff timing without a real test suite that takes
seconds to run — see `tests/test_http.py::test_get_json_uses_exponential_backoff_across_retries`.

## Why 404 is not an error

Confirmed with a real request during Stage 0 research: a nonexistent
article returns HTTP 404 with a JSON body like
`{"status":404,"title":"Not Found",...}`. If `get_json` raised on 404 like
every other error status, every "this article doesn't exist in this
language" case (a completely normal, expected outcome for this skill) would
look identical to a real outage. So 404 is data, not an exception — same
tier as 200, just with `status_code=404`.

## User-Agent

`build_session(contact)` sets `User-Agent: wiki-interest-trends/0.1
(+{contact})`. Wikimedia requires a meaningful contact in the UA;
`WIKITRENDS_CONTACT` (read by `wikitrends/cli.py`, not by `http.py` itself)
supplies it, with a placeholder default if unset.
