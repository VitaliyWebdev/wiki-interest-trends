# cache.py — SQLite response cache

**File:** `skills/wiki-interest-trends/scripts/wikitrends/cache.py`
**Tests:** `skills/wiki-interest-trends/tests/test_cache.py`

## What it's for

Satisfies the spec requirement that a repeat query about the same topic
doesn't hit the network. One SQLite file, one `cache` table
(`key TEXT PRIMARY KEY, value TEXT, expires_at REAL`), under
`~/.cache/wikitrends/cache.sqlite3` by default (override the directory with
`WIKITRENDS_CACHE`).

## Contract

```python
default_cache_path() -> Path        # WIKITRENDS_CACHE env var, else ~/.cache/wikitrends
cache_key(*parts) -> str            # stable sha256 over json.dumps(parts, sort_keys=True)
Cache(path=None, clock=time.time)
Cache.get(key) -> value | None      # None if missing OR expired (expired rows are deleted on read)
Cache.set(key, value, ttl_seconds=None)  # None = never expires
```

`value` is anything JSON-serializable — callers store parsed API responses
(dicts/lists), not raw text.

## TTL policy lives in the caller, not here

`cache.py` only knows "expire after N seconds" vs. "never". It has no idea
what a "month" or "current vs. closed period" means. That decision belongs
to whoever is fetching month-shaped data:

- `wikidata.py` (Stage 2): entities/sitelinks/redirects rarely change, so
  everything gets a flat 7-day TTL (`wikidata.CACHE_TTL_SECONDS`).
- `pageviews.py` (Stage 3, not built yet): a **closed** month's pageview
  count never changes → cache forever (`ttl_seconds=None`). The **current,
  still-accumulating** month changes every time Wikimedia recomputes it →
  short TTL. `pageviews.py` decides which case it's in per request; `cache.py`
  just executes whichever TTL it's given.

Keeping that decision out of `cache.py` is what makes it reusable for both
without a "kind of data" parameter leaking into the cache layer.

## Why the clock is injected

`Cache(clock=...)` defaults to `time.time` but tests pass a `FakeClock`
(a callable with a mutable `.now`, see `skills/wiki-interest-trends/tests/test_cache.py`). This lets TTL
expiry tests advance time instantly and deterministically instead of
calling real `time.sleep()` — the whole suite runs in ~0.08s.

## Key stability

`cache_key("wbsearchentities", {"lang": "uk", "q": "x"})` and
`cache_key("wbsearchentities", {"q": "x", "lang": "uk"})` produce the
**same** key — `json.dumps(..., sort_keys=True)` normalizes dict key order
before hashing. Without this, two callers building the same logical
request with a dict literal in a different field order would silently
miss the cache.
