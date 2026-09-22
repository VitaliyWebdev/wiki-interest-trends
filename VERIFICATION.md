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

All 8 scenarios in `evals/evals.json` were run for real against
`claude-haiku-4-5-20251001`, not simulated. Method: a scratch workspace
(`/tmp/wiki-eval-workspace`) with this skill symlinked in at
`.claude/skills/wiki-interest-trends` (so it's discovered as a real
project skill, not pasted into a prompt), invoked via
`claude --model haiku -p "<query>" --permission-mode bypassPermissions
--output-format json`. Multi-turn scenario used `--session-id` +
`--resume`. Full tool-call transcripts were read from each session's
`~/.claude/projects/.../<session-id>.jsonl` to see exactly what commands
Haiku ran, not just the final answer.

### Round 1 — 3 real bugs/gaps found and fixed in `SKILL.md`

**1. `scripts/resolve_topic.py: No such file or directory`.** Haiku's
first Bash call used the path from `SKILL.md`'s examples literally
(`uv run scripts/resolve_topic.py ...`), which only resolves if the shell
is already inside the skill's own directory — it wasn't (a real install is
symlinked into a project's `.claude/skills/`, cwd is the user's project).
Haiku recovered on its own (`ls`'d the directory, found it, `cd`'d in,
retried) but wasted a turn. First fix attempt: tell the agent to `cd` into
the skill directory. **That fix was itself wrong** — caught on the very
next run: `analyze.py`'s `wikitrends-out/` output directory is relative to
cwd, so `cd`-ing into the skill directory made output land *inside the
skill's own install location*, directly violating the spec's own
requirement that the skill directory may be read-only and outputs belong
in the caller's directory. Real fix: tell the agent to prefix commands
with the skill's absolute base directory *without* changing cwd. Verified
by re-running: the next transcript shows
`uv run /private/tmp/.../scripts/resolve_topic.py ...` (absolute path,
correct on the first try, no wasted turn) and
`wikitrends-out/<run-id>/` landing in `/tmp/wiki-eval-workspace/`, not
inside the skill's symlinked directory.

**2. A "which languages?" scoping question with no languages named in the
query got a chat question back, not an analysis.** For the "compare
English-learning interest across editions" prompt (task spec query 3,
which deliberately doesn't name languages), Haiku's first response was "I
propose to analyze X, Y, Z -- does this work for you?" with **zero tool
calls** -- it treated an open scoping decision the same way it (correctly)
treats genuine topic ambiguity. Fixed by adding an explicit rule
distinguishing the two: topic ambiguity (different real-world referents,
e.g. "Меркурій") always gets asked about; which languages to check, when
unspecified, is the agent's own judgment call to make and proceed with.
Re-run: picked 7 reasonable languages itself and completed the analysis.

**3. "Prepare a report" (a literal `SKILL.md` trigger word) didn't
trigger `report.py`.** Same query as above, after fix #2: Haiku produced
a good, well-formatted **chat** answer (a markdown table + grounded
recommendations) but never called `report.py`, despite the query literally
containing "звіт" (report) and `SKILL.md`'s own Step 4 saying to generate
a PDF when the user's words ask for a "report." The rule as written
("only if the user asked for a document/PDF/deck") apparently didn't read
as satisfied by "звіт" alone. Tightened the wording to explicitly name
"report"/"звіт"/"document"/"PDF"/"deck" and "anything to hand off or
share" as the trigger, and to say not to treat a chat answer as a
substitute. Re-run: called `report.py` and produced a real
`report.pdf`.

**Also found, not fixed (out of scope, documented instead):** analyzing
across `uk,pl,es,ja,ru,pt,de` logged
`UserWarning: Glyph ... missing from font(s) DejaVu Sans` for the Japanese
article title in the chart legend -- DejaVu has no CJK glyphs. Doesn't
break anything (stderr only, JSON contract unaffected), cosmetic only.
Documented in `docs/dev/chart-and-analyze-cli.md` as a "як розвивати
далі" item -- a CJK-capable font is several MB, disproportionate to fix
in scope for a legend-label edge case.

### Round 2 — all 8 scenarios, post-fix, real results

| Scenario | Turns | Result |
|---|---|---|
| `compare_langs` | 6 | Correct: found no Polish article (real, matches `sitelinks_q1666254_pl_cs_uk.json`), reported Czech YoY -53.6%, trend decreasing, trust high, with reasons. |
| `single_topic_trust` | 6 | Correct: astronomy interest in uk -59.6% raw / -45.5% normalized, trust high with all 5 reasons stated, correctly avoided a "no demand for the course" framing. |
| `compare_topics_report` | 6 | Correct after fix #2/#3: picked 7 languages itself, ran the full pipeline, called `report.py`, produced a real one-page `report.pdf`. |
| `ambiguous_topic` | 4 | Correct: surfaced all 5 real "Меркурій" candidates (planet/element/god/city/ship) and stopped to ask, did not guess. |
| `missing_language` | 5 | Correct: reported no Polish article as a real finding (localization gap), no crash, no fabricated number. |
| `low_traffic_niche_topic` | 5 | The chosen topic ("теорема Шпернера") turned out to have *no* Ukrainian article at all (not merely low-traffic) -- didn't exercise the low-trust path as designed, but handled the actual missing-language case correctly and proactively checked en/de coverage. Not re-run with a different topic; the missing-language path is already covered by scenario 5. |
| `news_spike_topic` | 6 | Correct and genuinely nuanced: solar eclipse interest in en -- YoY +22.9% but Mann-Kendall **not significant** (p=0.124), correctly identified periodic real-event spikes (Apr 2024 North American eclipse: 1.48M views vs. ~20-35k baseline), concluded "cyclical, not growing," trust medium. |
| `repeat_query_clarification` | 6 then **3** | Correct: turn 2 ("add Polish and Czech") went straight to `analyze.py --qids Q1666254 --langs uk,pl,cs --last 24m`, reusing the QID from turn 1 with zero calls to `resolve_topic.py`. |

7 of 8 scenarios validated the intended behavior directly; the 8th
(`low_traffic_niche_topic`) validated a different, already-covered path
instead of the intended one because of a topic-selection accident, not a
skill defect.

## Stage 11: real end-to-end run

Everything below was actually executed, not just planned:

- **All 3 scripts run for real via `uv run`**, using only each script's
  own PEP 723 metadata (not the dev venv) — done repeatedly through
  Stages 2/3/5/6 as each was built, and again for all 3 primary example
  queries via the real Haiku eval transcripts in Stage 9 (`compare_langs`,
  `single_topic_trust`, `compare_topics_report` above), which shows the
  exact commands an actual agent runs, not a hand-picked demo invocation.
- **Numbers cross-checked against pageviews.wmcloud.org** — done in
  Stage 8 (see above): 2 articles + 1 project total, all 3 exact matches.
- **Cache-hit path verified live**, not just by unit test call-counting:
  ran `analyze.py --qids Q1666254 --langs uk,cs --last 24m` three times
  against a fresh, empty cache directory. Run 1 (cold): 1.04s wall time,
  writes to `cache.sqlite3`. Runs 2 and 3 (warm): 0.34s wall time, and —
  the decisive check — `cache.sqlite3`'s mtime and byte size were
  **identical** before and after run 3, meaning zero writes happened,
  meaning zero cache misses, meaning zero network calls on a pure repeat
  query. (The unit tests already assert this via fake-session call counts
  per module; this is the same behavior confirmed against the real
  network and the real filesystem.)
- **Full eval suite run for real on Haiku 4.5** — Stage 9, above, all 8
  scenarios, 2 rounds (pre- and post-fix), with real fixes made to
  `SKILL.md` based on what actually happened, not adjustments to the
  evals to match whatever came out.

No new issues turned up in this final pass beyond what Stages 8/9 already
found and fixed.

## Stage 12: plugin + marketplace packaging, real install test

Requested after Stage 11: package this repo as an installable Claude Code
plugin with a self-hosted marketplace, so any user (not only developers
comfortable with git) can add it with two commands. Schema was fetched
directly from the live docs (`plugins-reference.md`,
`plugin-marketplaces.md`) rather than recalled, since the self-referential
`"source": "./"` case (marketplace and its one plugin in the same repo
root) isn't spelled out with a worked example in the docs — confirmed
instead from the docs' own text on relative-path resolution
("`Paths resolve relative to the marketplace root, which is the directory
containing .claude-plugin/`").

Done on a branch (`plugin-marketplace-restructure`) rather than directly
on `main`, per explicit request, so there's a rollback point.

**`claude plugin validate .`**: passed clean after one fix — the initial
`marketplace.json` had `description` at the top level, which the validator
rejected (`Unrecognized key: "description"`); moved it under `metadata.description`
per the validator's own suggested fix, then passed with zero warnings.

**Real install test, not just schema validation.** In a fresh scratch
workspace with no prior `.claude/skills/` setup at all:
```
claude plugin marketplace add /Users/user/wiki-interest-trends
claude plugin install wiki-interest-trends@wiki-interest-trends-marketplace
```
Both succeeded (`claude plugin list` showed it `✔ enabled`). Then ran a
brand-new query (Django, not used in any earlier eval) via
`claude --model haiku`: the transcript shows `Skill: wiki-interest-trends`
firing correctly, `uv run /Users/user/wiki-interest-trends/skills/wiki-interest-trends/scripts/resolve_topic.py`
and `analyze.py` running with the new nested path, and — the specific
thing this test needed to prove — `wikitrends-out/` landing in
`/tmp/plugin-test-workspace/` (the scratch workspace), not inside the
plugin/skill's own installed directory. Answer was correct (Django
interest in en: -41.66% YoY, high trust, correctly explained).

Test installation uninstalled and the test marketplace removed afterward,
so nothing was left behind in the real Claude Code config used for this
whole build.

(Note: `/plugin marketplace add ...` typed as a chat message inside `-p`
mode does **not** work — it's read as a request to invoke a skill literally
named "plugin" and fails with "Unknown skill: plugin". The actual
mechanism is the direct CLI subcommands used above,
`claude plugin marketplace add` / `claude plugin install`, run from a
shell — not slash-commands sent through a prompt. Interactive sessions
presumably intercept `/plugin ...` as a slash command before it reaches
the model; non-interactive `-p` mode does not.)
