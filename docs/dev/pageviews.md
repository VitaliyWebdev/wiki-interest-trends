# pageviews.py — fetching + normalizing pageview counts

**File:** `skills/wiki-interest-trends/scripts/wikitrends/pageviews.py`
**Tests:** `tests/test_pageviews.py`
**Fixtures:** `tests/fixtures/pageviews/*.json` — real recorded responses

## What it's for

The data-fetching layer `analyze.py` (Stage 5) will sit on top of: raw
per-article and project-wide pageview counts, normalized to a common scale.
No statistics here (that's `stats.py`, Stage 4) — just "get real numbers,
correctly".

## Contract

```python
encode_article_title(title: str) -> str
fetch_per_article(session, cache, project, article, start, end, granularity="monthly", *, today=None) -> PerArticleSeries
fetch_aggregate(session, cache, project, start, end, granularity="monthly", *, today=None) -> list[MonthlyPoint]
fetch_redirects_of(session, cache, lang, title) -> list[str]
normalize_series(article_points, aggregate_points) -> list[NormalizedPoint]
```

`PerArticleSeries(found: bool, points: list[MonthlyPoint])`,
`MonthlyPoint(timestamp, views)`,
`NormalizedPoint(timestamp, views, project_total, per_million)`.

## Two real gotchas found while building this (not from memory — from actual requests)

**1. `/` in an article title must be percent-encoded, or you get a false
"no data".** `encode_article_title` does
`quote(title.replace(" ", "_"), safe="")`. Tested against the real API:
requesting the title `AC/DC` with a naive encoder that leaves `/`
unescaped gets back `{"detail":"invalid route","status":404,...}` — a 404
that looks exactly like "no such article" but actually means "we built a
broken URL". `fetch_per_article` checks for this specific `detail` string
and raises `AppError(error_code="internal_request_error")` instead of
quietly reporting `found=False` — that distinction matters because a
silent `found=False` here would be a **wrong answer**, not a missing one.
See `tests/fixtures/pageviews/per_article_invalid_route.json` (captured by
deliberately mis-encoding a real request) vs.
`per_article_not_found.json` (a genuine "this article doesn't exist").

**2. Monthly granularity is not "whole calendar month" — it's "start date
to end date, bucketed by month".** If `end` falls in the middle of a
month, that month's `views` is the partial sum up to that day, not the
month's real total. Confirmed by three real requests for the same article
differing only in `end`: `.../20240401` → April = 9 views, `.../20240402`
→ April = 17, `.../20240430` → April = 767 (the real total). This is
actually *useful*: it's exactly what "the current incomplete month" means
in practice (`_ttl_for_end_date` gives that period a short TTL for exactly
this reason — the number is still climbing). But it means **Stage 5's
date-range construction must be deliberate**: if the caller wants N
*complete* months, `end` needs to be the last day of the last complete
month, not just "N months back from today" with an arbitrary day-of-month.
Using `date.today()` as `end` is correct specifically when the intent is
"include today's partial month" (which is the common case: "is interest
growing lately").

## TTL policy (concrete instance of the policy described in `docs/dev/cache.md`)

`_ttl_for_end_date(end, today)`: if `end`'s year-month is `>=` today's
year-month, short TTL (`CURRENT_PERIOD_TTL_SECONDS`, 6h); otherwise the
range is fully closed and cached forever (`ttl_seconds=None`). `today` is
an injected parameter (not `date.today()` called internally) purely so
tests are deterministic — see `test_ttl_for_end_date_is_short_for_the_current_month`.

`fetch_redirects_of` uses a flat 7-day TTL (`REDIRECTS_TTL_SECONDS`) — same
reasoning as `wikidata.py`'s sitelinks cache: redirect structure changes
rarely enough that a week-old answer is fine.

## `fetch_redirects_of` pagination

MediaWiki's `prop=redirects` paginates via `rdcontinue` for popular
articles. Real example: "Сполучені Штати Америки" (uk) has 23 redirects;
the recorded fixtures (`redirects_of_usa_page1.json` /
`..._page2.json`) were captured with `rdlimit=20`, which is why they split
20 + 3 — the code itself requests `rdlimit=500` (MediaWiki's documented max
for non-bot requests), so in production most articles will fit in a single
page and pagination is the exception, not the rule; the test fixtures just
happen to exercise the multi-page path since that's the more interesting
case to verify. `fetch_redirects_of` loops until a response has no
`continue.rdcontinue` key, accumulating `redirects[].title` from every
page. Not yet wired into anything that *uses* the redirect list
for `--include-redirects` summation — that assembly (fetch canonical
article + fetch each redirect + sum matching timestamps) is a couple of
lines of orchestration that belongs in `analyze.py` itself (Stage 5), not
here; `pageviews.py` only knows how to fetch one article's series at a
time.

## `normalize_series`

Pure function, no I/O: pairs each article point with the aggregate point
of the same `timestamp` and computes `views / project_total * 1_000_000`
("views per million project views"). A timestamp present in the article
series but missing (or zero) in the aggregate series is silently skipped
rather than raising — this would only happen from a caller bug (mismatched
date ranges between the two fetches), and skipping a point is safer than
crashing analysis over one gap or a division by zero.
