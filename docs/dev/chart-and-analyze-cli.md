# chart.py + analyze.py — putting it all together

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/chart.py`, `skills/wiki-interest-trends/scripts/analyze.py`
**Tests:** `skills/wiki-interest-trends/tests/test_chart.py`, `skills/wiki-interest-trends/tests/test_analyze.py`

## `chart.py`

```python
render_chart(series_by_label: dict[str, list[NormalizedPoint]], output_path: Path, title: str) -> None
```

One PNG, one line per label ("Article title (lang)"), each series's own
peak month annotated. Headless (`matplotlib.use("Agg")` — this only ever
runs from a CLI script, never a GUI). A label with an empty point list is
skipped when drawing, and `ax.legend()` only fires if at least one line
was actually plotted — an earlier version called `legend()` whenever the
*dict* was non-empty, which threw a `UserWarning` ("No artists with labels
found") whenever every requested topic/language turned out to have no
data; caught by `test_analyze_qids_mode_missing_language_reported_without_pageview_calls`
producing an empty `chart_series` dict flowing into a chart that still
needs to render (just an empty frame) without warnings.

Unit tests only check "produced a valid PNG, didn't crash" — chart.py has
no way to unit-test that the picture is *visually* right; that's what
Stage 11's real end-to-end run is for.

**Known limitation, found during the Stage 9 Haiku eval run (not
hypothetical — hit for real analyzing "English" across `uk,pl,es,ja,ru,pt,de`):**
DejaVu Sans (the only font shipped in `skills/wiki-interest-trends/assets/fonts/`) has no CJK glyphs.
An article title containing Chinese/Japanese/Korean characters in the
chart legend renders as missing-glyph boxes and matplotlib logs a
`UserWarning: Glyph ... missing from font(s) DejaVu Sans` on stderr. This
doesn't affect correctness (the underlying numbers/JSON are unaffected,
and the warning goes to stderr, never stdout, so it doesn't break the
`{"ok": ...}` contract) — it's a cosmetic gap for CJK-language legend
labels specifically. Not fixed: a CJK-capable font (e.g. Noto Sans CJK) is
several MB, multiple times the size of everything else this skill ships,
for a legend-label edge case. Flagged as a "как розвивати далі" item
rather than fixed in scope.

## `analyze.py` — the shape of the orchestration

This is the file that wires `wikidata.py` + `pageviews.py` + `stats.py` +
`trust.py` + `chart.py` together. Two ideas carry the whole design:

**1. A "target" is one (topic, language) pair**, built up front by
`_build_targets()` before any pageview fetching starts:
- `--qids` mode: for each QID, `get_sitelinks()` once for *all* requested
  langs (one Wikidata call per QID, not per QID-lang pair), producing a
  target per lang — `found: False, reason: "no_article_in_language"` for
  languages with no article, same "surface it, don't guess" spirit as
  `resolve_topic.py`.
- `--titles` mode: the caller already has exact titles in one language
  (typically a repeat query — see "repeat queries" in
  `docs/dev/wikidata-lookup-and-resolve-topic.md`), so this mode does zero
  Wikidata calls.

Building the full target list first (rather than resolving lazily while
analyzing) is what makes `test_analyze_two_different_qids_same_lang_shares_one_aggregate_call`
true: sitelinks lookups all happen in one batch, *then* pageview fetching
happens per target — so if two targets share a language, their
`fetch_aggregate()` calls share the same cache key and the second one
never hits the network. This ordering is a real behavior, not just an
implementation detail — it's asserted in the fixture call sequence in that
test.

**2. `found: False` carries a `reason`, never bare.** Two distinct reasons
exist: `"no_article_in_language"` (Wikidata has no sitelink) and
`"no_pageview_data"` (the article exists but the pageviews API had
nothing — e.g. too new, or renamed). Keeping these separate matters for
the agent's own explanation to the user; conflating them into one generic
"missing" would lose real information.

## Date range: `resolve_date_range()`

`--last 24m` resolves to **24 complete calendar months ending at the most
recently finished month** — not "24 months back from today's date". If
today is May 15, the most recent complete month is April, so `--last 3m`
gives Feb/Mar/Apr, not a range ending mid-May. This is the direct
consequence of the Stage 3 finding that monthly granularity returns a
*partial* sum for a month that `end` falls in the middle of — using
`date.today()` as `end` would silently understate the most recent month
every time, right when someone's asking "is this growing lately". `--last
Nd` (for daily granularity) doesn't have this problem and just uses
`end=today`.

Per-article data starts July 2015 (`EARLIEST_PER_ARTICLE_DATE`); a
`--start` before that is clipped with a warning surfaced both from
`resolve_date_range()` and in the final JSON's `warnings` field, per the
spec's explicit requirement to warn rather than silently truncate.

## Why YoY/seasonality are gated on `granularity == "monthly"`

`year_over_year_growth()` and `seasonality_ratio()` both assume each list
entry is one calendar month (see `docs/dev/stats-and-trust.md`). Running
them on a daily series would silently sum the wrong number of points into
a "12-month" bucket. `analyze.py` only calls them when
`granularity == "monthly"`; for daily data those fields come back `None` in
`analysis.json` rather than a wrong number. Theil-Sen/Mann-Kendall/peak
share work fine at any granularity (they only care about a value sequence,
not what a "month" means), so those run either way — just note that
Theil-Sen's slope is then "per day", not "per month".

## `analysis.json` vs. the compact stdout summary

Full per-series raw points, normalized points, every metric, and the full
trust reasons list go in `analysis.json`. Stdout gets one line per series
(`label`, `lang`, `qid`, `found`, and — only if found —
`yoy_growth`/`trend`/`trust_level`) plus the file paths, staying well
under the ~40-line budget regardless of how many topics/languages were
requested. `normalized_points` (the actual `NormalizedPoint` objects, kept
around only so `chart.py` doesn't need re-parsing dicts back into objects)
is stripped before writing `analysis.json` — asserted directly in
`test_analyze_qids_mode_found_article_writes_analysis_and_chart`.

## `--qids` vs `--titles`: a judgment call worth flagging

The spec's own line ("Вхід: один або кілька QID ... або назви статей,
--langs") doesn't fully pin down whether raw-titles mode should also
support multiple languages. Decided here: `--qids` is the multi-language
path (resolves per language via Wikidata), `--titles` is intentionally
single-language (the caller already has exact titles, comparing several
topics *within* one edition). Revisit if Stage 9 evals show Haiku actually
wants multi-language raw-titles.
