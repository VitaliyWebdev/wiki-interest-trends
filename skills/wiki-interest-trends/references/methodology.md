# Methodology

How `analyze.py` turns raw pageviews into growth numbers, a trend
verdict, and a trust level. Read this if a user asks *why* a result got a
particular trust level, or wants the statistical method explained -- not
needed for normal use of the skill.

## Normalization

Raw view counts aren't comparable across language editions of very
different sizes (English Wikipedia gets vastly more traffic than, say,
Czech Wikipedia, independent of any one topic). Every article's raw
monthly views are normalized against that language edition's **total**
monthly views for the same period:

```
per_million = article_views / edition_total_views * 1,000,000
```

i.e. "views per million views of that Wikipedia edition." Use
`yoy_growth_normalized` / `per_million` when comparing across languages;
raw numbers are fine for a single language over time.

## Year-over-year (YoY) growth

Sum of the most recent 12 months vs. the sum of the 12 months before that:

```
yoy_growth = (recent_12mo_sum - previous_12mo_sum) / previous_12mo_sum
```

Summing whole years specifically cancels out seasonality (a topic that
always spikes every December would look "volatile" month-to-month but
flat year-over-year, correctly). Requires 24 months of data; below that,
`yoy_growth` is `null` -- there isn't a second full year to compare
against. Also `null` if the earlier 12-month total was 0 (growth from zero
is undefined, not infinite).

## Trend: Theil-Sen slope + Mann-Kendall test

Two complementary numbers, both computed on `log(views)` to look at
*relative* change (view count doubling means the same thing whether a
topic gets 100 or 100,000 views/month):

- **Theil-Sen slope** (`theil_sen_slope_raw`/`_normalized`): the median of
  every pairwise slope between two months' log-views. Chosen specifically
  because it's robust to a handful of outlier months -- a perfect
  steady-growth series with one point replaced by a 1,000,000-view news
  spike still gives back essentially the same slope, where an ordinary
  least-squares fit would get dragged toward the spike. A single viral
  month shouldn't be able to masquerade as a change in the underlying
  trend.
- **Mann-Kendall test** (`mann_kendall`): a non-parametric test for
  whether a trend is real or could plausibly be noise, given the data's
  own variance -- with the standard tie correction, since low-traffic
  topics have a lot of repeated small integer view counts (ties are the
  common case here, not an edge case). Produces `trend`
  (`"increasing"`/`"decreasing"`/`"no trend"`), a `p_value`, and the raw
  `s_statistic`. `p_value < 0.05` is treated as significant.

Months with 0 views are dropped before taking the log (undefined at 0),
not treated as an error -- a real topic can have genuine zero-view months.

## Peak concentration

`peak_share_top2`: fraction of total views contributed by the two highest
months. A high value (roughly 50%+) means a small number of months --
plausibly a single news event -- account for most of the interest, which
is a very different situation from sustained, gradually growing interest
even if the raw growth number looks similar.

## Seasonality

`seasonality_ratio`: highest-average calendar month's views divided by the
lowest-average calendar month's, computed from the actual calendar month
of each data point. `null` under 24 months of data -- with only one
sample per calendar month, there's no way to tell a real seasonal pattern
from a single unrelated spike that happened to land in, say, October.

## Trust level: high / medium / low

A **deterministic rule in code**, not a judgment call left to the calling
model -- the whole point of running this analysis in Python instead of in
an LLM's own reasoning. Five checks, each contributing at most one
"concern":

1. **Series length** -- below 24 months is a concern (can't do a full
   year-over-year comparison); below 12 months, trust is `"low"`
   immediately, no trend is even attempted.
2. **View volume** -- average monthly views below 30 is a concern (small
   numbers are noisy); below 100 is a milder concern.
3. **Trend significance** -- Mann-Kendall p-value >= 0.10 is a concern
   (not significant); >= 0.05 is a milder concern (weakly significant).
4. **Normalized vs. raw agreement** -- if the raw trend and the
   traffic-normalized trend point in different directions, that's a
   concern: the raw number might just be tracking the language edition's
   own overall growth or decline, not real interest in the specific topic.
5. **Peak concentration** -- `peak_share_top2` >= 0.5 is a concern (likely
   a spike, not sustained interest); >= 0.35 is milder.

**Level = concern count**: 0 concerns -> `high`, 1 -> `medium`, 2+ ->
`low`. No weighting, no per-factor score -- deliberately the simplest rule
that satisfies "a rule in code decides this, not the model calling it."

Every reason (both the concerns *and* the things that went well) is
attached to the result in `series[].trust.reasons` (rendered English text)
and `series[].trust.reason_codes` (code + parameters, which `report.py`
renders in the report's own language) -- never just the bare level with no
explanation.

Thresholds are reasoned defaults (documented as named constants in
`scripts/wikitrends/trust.py`), not calibrated against a labeled dataset --
none exists for this task. If real usage (via evals or actual queries)
shows a threshold is miscalibrated, adjust the constant; the rule's
*structure* (deterministic, reason-per-factor) shouldn't need to change.
