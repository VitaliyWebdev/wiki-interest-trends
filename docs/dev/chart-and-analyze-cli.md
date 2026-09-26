# chart.py + analyze.py — putting it all together

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/chart.py`, `skills/wiki-interest-trends/scripts/analyze.py`
**Tests:** `skills/wiki-interest-trends/tests/test_chart.py`, `skills/wiki-interest-trends/tests/test_analyze.py`

## `chart.py`

```python
render_chart(series_by_label: dict[str, list[dict]], output_path: Path, lang: str = "en") -> None
```

One chart, one line per label ("Article title (lang)"). The file format
follows `output_path`'s suffix: `analyze.py` writes `chart.png` for chat,
and `report.py` writes a temporary PDF and stamps it onto the report as
vector graphics. Points are `analysis.json`'s own `series[].normalized`
dicts (`timestamp`, `per_million`, ...), not `NormalizedPoint` objects,
so `analyze.py` and `report.py` draw from the exact same data, and
`chart.py` doesn't import `pageviews.py` (which would drag `requests`
into `report.py`'s PEP 723 environment). Every string comes from
`CHART_LABELS[lang]` and month names from `i18n.MONTHS_SHORT` (see
`i18n.md`); `analyze.py` draws its `chart.png` in the default language,
and `report.py` redraws its own in the report's language. Headless
(`matplotlib.use("Agg")` — this only ever runs from a CLI script, never
a GUI).

What it draws, and why each choice was made, is in `report-design.md`:
views per million for one series, an index (100 = the series' own
average) for several; line-end labels instead of a legend; peak markers
whose labels drop out rather than collide; a shaded "last 12 months"
band for monthly data. Two contracts other code relies on:

- **Colors follow the dict's order** (`theme.series_color(i)`), and a
  label with no points still takes its color slot. `report.py` colors
  each series' card and table sparkline by the same index.
- **Text stays text.** `pdf.fonttype: 42` embeds TrueType, and halos are
  drawn as separate white copies instead of path effects (which turn text
  into outlines). `test_chart.py` relies on that: it renders to PDF and
  reads back what was actually drawn, instead of the old "produced a
  valid PNG, didn't crash" checks.

A label with an empty point list draws nothing. An empty dict still
renders a titled "No data to plot" frame without warnings, which
`test_analyze_qids_mode_missing_language_reported_without_pageview_calls`
exercises (every requested language missing).

Chinese/Japanese/Korean line labels used to render as missing-glyph
boxes (DejaVu Sans has no CJK; found in the Stage 9 Haiku eval run on
`uk,pl,es,ja,ru,pt,de`). Fixed in Stage 15: `render_chart` sets
`font.family` to DejaVu Sans plus the bundled CJK fonts, and matplotlib
falls back per glyph. See `fonts.md` for the font choice and the one
ordering trap (Hangul split into jamo).

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
requested. `series[].normalized` is part of the contract, not just a
debug dump: `report.py` redraws the chart from it, which
`test_analyze_qids_mode_found_article_writes_analysis_and_chart` asserts.
(An earlier version also carried a `normalized_points` copy as
`NormalizedPoint` objects just for `chart.py`, stripped before writing the
JSON; `chart.py` now takes the dicts directly, so that copy is gone.)

## `--qids` vs `--titles`: a judgment call worth flagging

The spec's own line ("Вхід: один або кілька QID ... або назви статей,
--langs") doesn't fully pin down whether raw-titles mode should also
support multiple languages. Decided here: `--qids` is the multi-language
path (resolves per language via Wikidata), `--titles` is intentionally
single-language (the caller already has exact titles, comparing several
topics *within* one edition). Revisit if Stage 9 evals show Haiku actually
wants multi-language raw-titles.
