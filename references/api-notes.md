# API notes

Wikimedia/Wikidata API behavior this skill's code depends on, confirmed
with real requests (not from documentation alone) during development. Read
this if you're extending the skill or debugging an unexpected result --
normal use of `resolve_topic.py`/`analyze.py`/`report.py` doesn't require
it.

Official reference:
https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html

## Wikidata search and entities

`action=wbsearchentities` (wikidata.org) -- search by a label in any
language. Returns up to `limit` candidates with `id`, `label`,
`description`. This is genuinely ambiguous for common words: searching
"Меркурій" (uk) returns five real, unrelated Wikidata items sharing that
label -- the planet, the chemical element, a Roman god, a US city, and a
warship. The skill never picks one automatically; see `SKILL.md`.

`action=wbgetentities&props=sitelinks` -- **a language with no article
simply has no key** for that wiki in the `sitelinks` object (e.g. no
`plwiki` key at all if there's no Polish article). There is no explicit
"missing" flag from the API; `wikidata.py` synthesizes one. Use
`sitefilter=langwiki|langwiki2|...` to restrict the response to only the
languages you need -- without it, a well-covered topic returns sitelinks
for every Wikipedia it has (~200 possible keys), most of which you'd throw
away.

An **invalid QID returns HTTP 200** with an `{"error": {...}}` body, not a
404 or a network-level failure. Must be checked explicitly.

## Redirects

`action=query&titles=<title>&redirects` resolves a title to its canonical
form (follows one redirect).

`action=query&titles=<canonical title>&prop=redirects&rdlimit=<n>` lists
the redirects pointing *at* a canonical title (used for
`--include-redirects`). Paginates via `continue.rdcontinue` when a title
has more redirects than fit in one response -- loop until a response has
no `continue` key.

## Pageviews REST API

Per-article:
`/metrics/pageviews/per-article/{project}/all-access/user/{article}/{granularity}/{start}/{end}`

Aggregate (project totals, for normalization):
`/metrics/pageviews/aggregate/{project}/all-access/user/{granularity}/{start}/{end}`

The `user` agent segment filters out bots/spiders -- always use it, never
`all-agents`, or bot traffic (which can dwarf real interest for some
articles) pollutes every number downstream.

**Article title encoding: replace spaces with `_`, then percent-encode
everything including `/`.** Confirmed with a real request: a title like
"AC/DC" with `/` left unescaped is read by the API as a path separator and
returns `404 {"detail": "invalid route", ...}` -- indistinguishable by
status code alone from a genuine "no data" 404 (`{"detail": "The date(s)
you used are valid, but we either do not have data...", ...}`). The skill
checks the `detail` string specifically to tell these apart
(`pageviews.py`'s `fetch_per_article`) and raises `internal_request_error`
for the "invalid route" case rather than silently reporting "no data".

**404 for a genuinely missing article is a normal result, not a
failure** -- handled as `PerArticleSeries(found=False, points=[])`, never
raised as an error.

**Monthly granularity is "sum from `start` to `end`, bucketed by
calendar month" -- not "the whole calendar month" if `end` falls mid-month.**
Verified with three real requests for the same article differing only in
`end`: `.../20240401` -> that month's `views` = 9 (partial), `.../20240402`
-> 17, `.../20240430` (the actual last day) -> 767 (the real total).
`analyze.py`'s `resolve_date_range()` always resolves `--last Nm` to N
*complete* calendar months ending at the most recently finished month for
exactly this reason -- see `docs/dev/pageviews.md` and
`docs/dev/chart-and-analyze-cli.md` for the full reasoning.

Per-article pageview data starts **July 2015**; requests starting earlier
get clipped with a warning (`analyze.py`'s `EARLIEST_PER_ARTICLE_DATE`),
per the spec.

## Rate limits and retries

No explicit rate-limit headers (`Retry-After`, `X-RateLimit-*`) were
observed during development, and no 429/5xx was actually triggered. The
skill's retry logic (`wikitrends/http.py`) is written defensively per the
task's own requirement -- exponential backoff on 429 and 5xx, immediate
(non-retried) handling of 404 and other 4xx -- rather than tuned against
an observed rate limit, since none was found to tune against. Responses do
carry `cache-control: s-maxage=14400` (4h) from Wikimedia's own edge.

## User-Agent

Wikimedia asks for a meaningful contact in the `User-Agent`. Set via
`WIKITRENDS_CONTACT` (an env var, read by `wikitrends/cli.py`); falls back
to a placeholder string if unset. `wikitrends/http.py`'s `build_session()`
constructs the header as `wiki-interest-trends/0.1 (+{contact})`.
