# stats.py + trust.py — the numbers an agent can't sanity-check itself

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/stats.py`, `skills/wiki-interest-trends/scripts/wikitrends/trust.py`
**Tests:** `skills/wiki-interest-trends/tests/test_stats.py` (20), `skills/wiki-interest-trends/tests/test_trust.py` (8)

## Why this is the highest-stakes module in the skill

Every other module fails loudly (an exception, an `AppError`) or is easy
to eyeball (a chart, a list of article titles). Bad statistics fail
*silently* — a wrong slope or an overconfident trust level just looks like
a normal answer, and Haiku has no way to catch it. So `stats.py` is pure,
dependency-free functions (`List[float] -> float`, no I/O, no classes to
misuse) that are cheap to test exhaustively against inputs with a
mathematically known correct answer — not just "looks plausible" outputs.

## `stats.py` — all pure functions over `List[float]` (except one)

```python
year_over_year_growth(values: list[float]) -> float | None
theil_sen_log_slope(values: list[float]) -> float | None
mann_kendall_test(values: list[float], alpha=0.05) -> MannKendallResult
peak_share(values: list[float], top_n=2) -> float | None
average_monthly_views(values: list[float]) -> float
seasonality_ratio(points: list[MonthlyPoint]) -> float | None  # the one exception, needs calendar months
```

Every function but `seasonality_ratio` takes a plain `list[float]`, not
`MonthlyPoint`/`NormalizedPoint` — deliberately, so the exact same function
runs on raw views *and* on normalized per-million values without a
parallel "normalized" variant of each. `analyze.py` (Stage 5) will call
e.g. `theil_sen_log_slope([p.views for p in raw])` and
`theil_sen_log_slope([p.per_million for p in normalized])` and compare the
two signs — that comparison is one of the five trust inputs. Only
`seasonality_ratio` needs `MonthlyPoint` specifically, because "which
calendar month" only exists on the raw timestamped series.

**`year_over_year_growth`**: sums the most recent 12 months and the 12
before that, returns `(recent - previous) / previous`. Summing whole years
is what cancels seasonality — a month-over-month delta wouldn't. `None`
below 24 months (can't form two full years) or when the earlier period
totaled 0 (growth from zero is undefined, not infinite — returning `None`
forces the caller/report to say "can't compute" instead of printing `inf`
or `9900%`).

**`theil_sen_log_slope`**: median of every pairwise slope of `log(views)`
vs. month index. Chosen over ordinary least-squares specifically for
robustness — verified with a synthetic case
(`test_theil_sen_is_robust_to_a_single_huge_outlier`): a perfect
`ln(2)`-per-month series with one point replaced by a 1,000,000-view spike
still gives back `ln(2)` almost exactly from Theil-Sen, while a quick
side-by-side OLS calculation on the same data jumps from `0.69` to `2.17`
— a single viral month would not silently masquerade as a change in the
underlying trend. Zero-view months are dropped before taking the log
(log(0) is undefined) rather than treated as an error — a real topic can
have genuine zero-view months.

**`mann_kendall_test`**: standard non-parametric trend test, *with* the
tie correction (`Var(S)` adjustted for repeated values) — not the naive
formula, because low-traffic series (small integers repeating: 0, 1, 2...)
have ties as the common case, not an edge case, for exactly the kind of
niche topic this skill is often asked about. Returns `trend` +
`p_value` + `s_statistic`, not just the verdict, so both tests and the
final report can show the evidence. All three example synthetic series
(strictly increasing, strictly decreasing, constant, alternating) were
cross-checked against an independently written reference calculation
before being hardcoded as expected test values — not just "whatever the
implementation outputs".

**`peak_share`**: total views claimed by the top-N months. Directly
detects "one news cycle looks like sustained growth" — a real risk the
spec calls out explicitly.

**`seasonality_ratio`**: peak calendar month's average ÷ quietest calendar
month's average, using the actual month parsed out of each point's
`timestamp` (not a fragile "which index is January" parameter). `None`
under 24 months — with only one sample per calendar month there's no way
to tell a seasonal pattern from a single unrelated spike that happened to
land in, say, October.

## `trust.py` — the deterministic high/medium/low rule

```python
assess_trust(*, months_of_data, avg_monthly_views, mk_p_value,
             raw_slope_sign, normalized_slope_sign, peak_share_top2) -> TrustAssessment
```

`TrustAssessment(level, reasons)` — `reasons` is never empty, even for
`"high"`: every check appends either a strength or a concern, so the
report always has something to say about *why*, not just the label.

**Update (Stage 6):** `reasons` is `List[Reason]`, not `List[str]`.
`Reason(code, params)` is structured, not a pre-formatted English
sentence — `render_reason(reason, lang)` renders it from
`REASON_TEMPLATES[code][lang]`, with English as the fallback for an
unsupported language (the shared `i18n.pick` rule — see `i18n.md`). This changed after `report.py` was actually run and
produced a Ukrainian-language report with the limitations section stuck in
English (the reasons were hardcoded English strings); see
`docs/dev/report-pdf.md` for the full story. `analyze.py` writes both
`trust.reasons` (rendered English, for a human skimming `analysis.json`)
and `trust.reason_codes` (code+params, for `report.py` to localize) into
the JSON. Each `reason_codes` entry also carries `"concern": true|false`,
set by `assess_trust()` itself (`Reason.concern`), so the PDF can mark
each reason ✓ / ! without re-deriving these rules.
`test_every_reason_says_whether_it_counts_against_the_level` checks the
flags reproduce the level (concern count 0/1/2+). `render_reason` shows a
p-value below 0.001 as "p<0.001" rather than the "p=0.000" the `.3f`
format used to give.

**The rule, spelled out** (matches the five factors the spec names
explicitly): below 12 months of data, short-circuit straight to `"low"` —
there isn't enough history to even attempt a trend. Otherwise, check five
things, each contributing at most one concern: series length (<24mo),
view volume (<30/mo low, <100/mo moderate), Mann-Kendall significance
(p>=0.10 not significant, p>=0.05 weakly significant), whether the raw and
normalized trend directions agree, and whether the top-2 months are
>=50% (or >=35%) of total views. **Level is just a concern count**: 0 →
`high`, 1 → `medium`, 2+ → `low`. No weighting, no per-factor score to
tune — deliberately the simplest rule that satisfies "code decides, not
the model", and every threshold is a named constant at the top of the
file rather than buried in the logic, so this is where you touch it if
the thresholds prove wrong once evals + Stage 11 real testing run.

Thresholds (`LOW_VOLUME_AVG_VIEWS=30`, `HIGH_VOLUME_AVG_VIEWS=100`,
`PEAK_SHARE_HIGH=0.5`, `PEAK_SHARE_MODERATE=0.35`,
`SIGNIFICANCE_ALPHA=0.05`, `WEAK_SIGNIFICANCE_ALPHA=0.10`) are reasoned
defaults, not calibrated against a labeled dataset (none exists for this
task) — flagged here so Stage 9/11 real-world runs are the place to
sanity-check them against actual topics, not treat them as settled.
