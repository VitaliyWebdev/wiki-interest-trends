# Verification log

What was checked, how, and what got fixed as a result. This is the log a
reviewer checks to see that claims in this repo were verified, not just
asserted — per the task's own requirement.

## Stage 8: spot-check against pageviews.wmcloud.org

Compared numbers this skill's own fixtures/output produce against the
independent, well-known https://pageviews.wmcloud.org tool (same
underlying Wikimedia data, different codebase), for the same articles and
date range used throughout development (`Інтервальне голодування`,
`Меркурій (планета)`, uk.wikipedia, January-April 2024, monthly).

| Check | This skill | pageviews.wmcloud.org | Match |
|---|---|---|---|
| "Інтервальне голодування" total views, Jan-Apr 2024 | 223+285+313+767 = **1588** | **1 588** | exact |
| "Меркурій (планета)" total views, Jan-Apr 2024 | 11939+8405+4864+4326 = **29534** | **29 534** | exact |
| uk.wikipedia project total, Jan 2024 (used for normalization) | **115282138** | **115 282 138** | exact |

All three exact matches. This confirms both the per-article fetch
(`pageviews.py::fetch_per_article`) and the aggregate/normalization fetch
(`fetch_aggregate`) are pulling and reporting the same numbers Wikimedia's
own analytics UI shows — not just internally self-consistent, but correct
against an independent source.

No fixes were needed as a result of this check (everything matched on the
first check) — recorded here as the check itself, per the spec's explicit
requirement to do this and log it, not because it turned anything up.

## Stage 6: PDF report, visual inspection

`report.py`'s output was rendered to PNG (`qlmanage -t`, macOS Quick Look)
and actually looked at, twice — not just checked for "1 page" via `pypdf`.
This is what caught two real bugs unit tests didn't: a missing transitive
`requests` dependency in `report.py`'s own PEP 723 metadata, and trust
reasons hardcoded in English appearing inside an otherwise Ukrainian
report. Both fixed; see `docs/dev/report-pdf.md` for the full story and
`docs/dev/stats-and-trust.md` for the `trust.py` rework this caused.

## Stage 9: Haiku 4.5 eval run

(To be filled in once `evals/evals.json` exists and the real run happens.)
