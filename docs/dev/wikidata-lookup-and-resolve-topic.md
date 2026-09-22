# wikidata.py + resolve_topic.py — topic → QID → article titles

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/wikidata.py`, `skills/wiki-interest-trends/scripts/resolve_topic.py`
**Tests:** `tests/test_wikidata.py`, `tests/test_resolve_topic.py`
**Fixtures:** `tests/fixtures/wikidata/*.json` — real recorded Wikidata API responses (see below)

## What it's for

Turns a fuzzy natural-language topic into a Wikidata QID, and a QID into
per-language Wikipedia article titles. `resolve_topic.py` is the CLI an
agent calls once per *new* topic; once it has a QID it can call
`analyze.py` directly with that QID on later requests (re-resolving isn't
needed — see "repeat queries" below).

## `wikidata.py` — three functions, all cached (7-day TTL, `CACHE_TTL_SECONDS`)

```python
search_entities(session, cache, query, language, limit=5) -> list[Candidate]
get_sitelinks(session, cache, qid, langs) -> dict[lang, ArticleLookup]
resolve_redirect(session, cache, lang, title) -> str
```

`Candidate(qid, label, description)`, `ArticleLookup(status, title=None)`
where `status` is `"found"` or `"missing"`.

**`search_entities`** wraps Wikidata's `wbsearchentities`. It returns
*every* candidate the API gives back (up to `limit`), in the API's own
order — it does **not** try to guess which one is "right". That's a
product requirement, not an oversight: `search "Меркурій"` (uk) really does
return 5 genuinely different topics sharing that label — the planet, the
chemical element, the Roman god, a US city, and a warship (see
`tests/fixtures/wikidata/search_mercury_uk.json`, captured from a real
request). Picking one silently would just be a coin flip dressed up as
intelligence; surfacing all of them lets the agent read the descriptions
and ask the user.

**`get_sitelinks`** wraps `wbgetentities` with `props=sitelinks` and,
importantly, `sitefilter=plwiki|cswiki|...` — restricting the response to
only the requested language editions. Without `sitefilter` the API returns
sitelinks for every Wikipedia the topic has an article in (~200 possible
keys for a well-covered topic); filtering server-side avoids a payload we'd
have to throw most of away anyway. **A missing language is not flagged by
the API** — there is simply no `plwiki` key in `sitelinks` at all if the
topic has no Polish article. `get_sitelinks` turns "key absent" into an
explicit `ArticleLookup(status="missing")`, so nothing downstream has to
special-case a missing dict key. An invalid QID gets a `200 OK` response
with an `{"error": {...}}` body (not a 404 — confirmed with a real request,
see `tests/fixtures/wikidata/sitelinks_invalid_qid.json`); `get_sitelinks`
turns that into `AppError(error_code="qid_not_found")`.

**`resolve_redirect`** wraps MediaWiki's `action=query&redirects` to
normalize a title to its canonical form. Not currently called by
`resolve_topic.py` itself (Wikidata sitelinks already point at canonical
titles in practice), but lives in `wikidata.py` because `pageviews.py`
(Stage 3) will need it for the `--include-redirects` case, and because a
title the *agent* supplies directly to `analyze.py` (bypassing
`resolve_topic.py`) might be a redirect.

## `resolve_topic.py`

```python
resolve_topic(session, cache, query, query_lang, langs, limit=5) -> dict
```

For each candidate from `search_entities`, calls `get_sitelinks` and
assembles:

```json
{
  "ok": true,
  "candidates": [
    {
      "qid": "Q1666254",
      "label": "intermittent fasting",
      "description": "a diet that cycles between a period of fasting and non-fasting",
      "articles": {
        "pl": {"status": "missing"},
        "cs": {"status": "found", "title": "Přerušovaný půst"}
      }
    }
  ]
}
```

If `search_entities` returns zero candidates, `get_sitelinks` is never
called (see `test_resolve_topic_returns_empty_candidates_without_extra_lookups`)
— no point looking up article titles for topics that don't exist.

## Repeat queries

Per the spec: once the agent has a QID for a topic, a follow-up request
(different date range, one more language, etc.) should be fast because of
the cache, using *the same QID*. Concretely: the agent does **not** need to
call `resolve_topic.py` again — it calls `analyze.py` directly with
`--qids Q1666254 --langs pl,cs,uk`, and `analyze.py` (Stage 3+) calls
`get_sitelinks` itself, which hits the 7-day cache instead of the network.
`resolve_topic.py` is only for the *first* time a topic's identity is
ambiguous.

## Fixtures

All `tests/fixtures/wikidata/*.json` are real API responses captured
during Stage 0/2 research (`curl` against `wikidata.org` /
`{lang}.wikipedia.org`, saved verbatim), not hand-written — so the tests
exercise the actual response shape (key names, nesting, the exact form of
an error body), not an assumption about it.
