# Interpreting results

Worked examples of turning `analyze.py`'s JSON into a good answer, and
edge cases worth knowing about. Read this if a result looks surprising and
you're not sure how to phrase it -- `SKILL.md`'s "How to write
conclusions" section covers the baseline rules; this goes deeper.

## Good vs. bad conclusion wording

| Situation | Bad | Good |
|---|---|---|
| Growth is real and trust is high | "There's huge demand for X!" | "Interest in X grew 42% year-over-year in the Ukrainian edition, and this trend looks reliable (high trust: 30 months of data, statistically significant, holds after normalizing for the edition's own traffic)." |
| Growth is real but trust is low | "Interest in X is growing." (stated flatly, matching how you'd phrase a high-trust result) | "Interest in X appears to be growing (+65% raw), but I'd treat that cautiously -- only 8 months of data and average views are quite low, so this could easily be noise rather than a real trend." |
| A language has no article | (silently omitted from the answer) | "There's no Polish Wikipedia article on X at all -- that itself is worth noting if Poland is a market you're considering; there's no existing reference content to build interest from." |
| Comparing two languages by raw views | "X gets way more attention in English than in Czech" (comparing 50,000 vs. 500 raw views) | Compare `per_million`, not raw counts -- English Wikipedia has far more total traffic than Czech, so raw counts alone mostly measure edition size, not topic interest. |
| A single big spike | "Interest in X tripled this year!" | Check `peak_share_top2` first. If it's high, this may be one news event, not sustained interest -- say so: "Views spiked sharply in March (likely a specific event), but outside that spike, interest looks flat/declining." |

## Trust level in your own words

Don't just print "trust: medium" -- translate the reasons into what they
actually mean for the user's decision:

- **High**: "This is a reliable read -- enough history, enough traffic,
  a statistically real trend that isn't just an artifact of Wikipedia's
  own growth or a single news spike."
- **Medium**: name the *one* thing holding it back (per the trust rule,
  medium always means exactly one concern) -- e.g. "reliable trend, but
  only 18 months of history so far, so I'd revisit this in a few months."
- **Low**: be direct that the number shouldn't drive a decision on its
  own -- "there's a signal here, but with this little data I wouldn't
  treat -34% as a confirmed decline; it could easily reverse."

## Seasonality

If `seasonality_ratio` is notably above 1 (say, 3+), a topic's viewership
swings a lot by calendar month on its own, independent of any real trend
-- back-to-school topics every September, tax topics every spring, etc.
This isn't a problem for `yoy_growth` (summing full years cancels it out
by design), but it matters if you're eyeballing the chart or explaining
why a particular month looks like a spike when it's actually a recurring
pattern. Mention it if it's relevant to the user's question, e.g. "note
that interest in this topic always rises every $season, so the recent
uptick may partly be the usual seasonal pattern rather than something new."

## Ambiguous topics

If `resolve_topic.py` returns multiple candidates with clearly different
`description`s (see the real "Меркурій" example in `references/api-notes.md`
-- planet, element, Roman god, a US city, a warship, all sharing that
label), **stop and ask the user which one they meant** before calling
`analyze.py`. Don't guess based on which seems most likely, and don't
default to the first result -- the search API's ranking is not a
disambiguation signal.

If the candidates are clearly all describing the *same* real-world thing
(e.g. minor label/alias variations), it's reasonable to proceed with the
first one, but say which QID/description you used so the user can correct
you if wrong.

## Very short or very low-traffic series

A topic with under 12 months of data or very few views per month will
come back `trust: "low"` with `months_of_data`/volume-related reasons.
This is expected and correct behavior, not a bug to work around by
lowering your bar for what counts as a trend -- if the user pushes back,
explain that Wikipedia simply doesn't have enough signal yet for this
particular topic/language, and that's itself useful information (maybe
too niche a topic, or too new).

## When the numbers seem to contradict the chart

`analyze.py`'s chart shows normalized (`per_million`) values; the metrics
table and `yoy_growth_raw` use raw or normalized depending on which field
you're looking at. If a raw-vs-normalized trend direction disagrees (flagged
directly in the trust reasons as `trend_reverses_after_normalization`),
that itself is the finding -- the raw number is likely tracking the whole
language edition's growth or decline (e.g. a language edition's overall
readership is falling), not anything specific to the topic. Lead with that
explanation rather than picking one number to report and ignoring the
disagreement.
