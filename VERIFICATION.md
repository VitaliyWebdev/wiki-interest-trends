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

### Real-world confirmation: desktop app GUI "Add marketplace" fails for the user

After the CLI install was verified working (above), the user tried the
desktop app's own "+" → Plugins → "Add marketplace" dialog for real, with
this repo's HTTPS URL. It failed with a generic "Failed to add
marketplace" error. Separately, after the marketplace *was* successfully
registered via the CLI (`claude plugin marketplace list` showed it), it
did not appear when the user searched "wiki" in the desktop app's
"Discover" tab.

Researched both symptoms against public GitHub issues rather than
guessing:

- **"Failed to add marketplace"** matches
  [anthropics/claude-code#77927](https://github.com/anthropics/claude-code/issues/77927)
  exactly: the desktop GUI's marketplace-add flow prefers an SSH clone
  (`git@github.com:owner/repo.git`) in a non-interactive spawned process
  with no usable `ssh-agent`, hangs, and is killed after a ~60s timeout,
  surfaced as an unactionable `MARKETPLACE_ERROR:UNKNOWN`. The identical
  operation via the CLI (`claude plugin marketplace add owner/repo`)
  succeeds in seconds, because the terminal has real SSH credential
  access. **Closed by Anthropic as "not planned"** — not something fixable
  from this repo's side (`claude plugin validate .` already passes
  clean, confirming the manifests themselves aren't the problem).
- **Discover tab not showing the custom marketplace's plugin** matches
  [anthropics/claude-code#43745](https://github.com/anthropics/claude-code/issues/43745):
  custom/self-hosted marketplace plugins are known to desync between the
  "Installed" and "Discover" tabs, and the marketplace auto-sync
  mechanism does a `git fetch` but never a `git pull`, leaving the cache
  stale. Closed as a duplicate of broader marketplace-sync issues,
  also unresolved.

**Conclusion:** these are confirmed, reported, currently-unfixed bugs in
Claude Code Desktop's own plugin-marketplace UI — general to any
custom/self-hosted marketplace, not specific to this repo — not a defect
in this skill's packaging. Any user trying the GUI-only path is likely to
hit the same wall. `README.md` was updated to lead with the CLI install
method (proven reliable twice, above) and explicitly flag the GUI path as
currently broken, with sources, rather than let users bounce off an
undocumented dead end.

## Stage 12b: audit against the Agent Skills spec + original task structure

User asked directly whether the skill was implemented correctly against
https://agentskills.io/specification and the original task's own required
layout, before doing anything further. Audited rather than asserted:

- `claude plugin validate .` — passes clean.
- `tests/test_skill_md.py` (6 automated checks: name regex + directory
  match, description length/no angle brackets, compatibility length, body
  line budget, every referenced file/script actually exists) — all pass.
- **Found a real gap**: the original task spec lists `requirements.txt`
  and `tests/` as siblings of `SKILL.md` *inside* the skill directory;
  Stage 12 had left both at the repo root as general "dev tooling" (a
  reasonable-sounding call that turned out to be wrong for these two
  specifically, since they're literally named in the task's own file
  tree, unlike `docs/dev/`/`DEV_PLAN.md`/`evals/`, which aren't).

Fixed (Stage 12b in `DEV_PLAN.md`): moved `tests/`, `conftest.py`,
`requirements.txt` into `skills/wiki-interest-trends/`. Added `pytest.ini`
at the repo root (`testpaths = skills/wiki-interest-trends/tests`) so the
documented root-level `pytest` workflow is unaffected.

**Verified twice, for real, not just by re-running the suite in place:**
1. `pytest` from the repo root: 124 passed.
2. `pytest` invoked from *inside* `skills/wiki-interest-trends/` directly: 124 passed.
3. **The actual standalone-ness claim**: copied *only*
   `skills/wiki-interest-trends/` into an empty temp directory (no `.git`,
   no `docs/`, no `DEV_PLAN.md`, nothing else from this repo) and ran
   `uv run scripts/resolve_topic.py --query "test" ...` from there —
   real Wikidata data came back, proving the directory is genuinely
   self-contained per the spec's "a directory containing, at minimum, a
   SKILL.md file" bar, not just structurally similar to one.

`claude plugin validate .` re-run after the move — still passes clean.

## Stage 12c: a second real user hit the same false "network policy" diagnosis

An unrelated person who installed the skill independently hit
`network_error` and their agent session concluded, without further
verification, that their org's network policy blocked
wikidata.org/wikimedia.org -- the exact same false conclusion an earlier
session reached about the maintainer's own machine (disproved at the time
by a direct `curl` test that worked fine). Since a stranger using this
skill has no way to reach the maintainer for the same debugging
walkthrough, the fix had to move into the skill itself rather than stay
as tribal knowledge: `network_error`'s `hint` now gives the agent an exact
`curl` command to verify with before concluding anything about the user's
network, echoed in `SKILL.md`'s error table and
`references/interpreting.md` with this incident as the worked example.
Locked in with a test asserting the hint actually contains the `curl`
command, not just generic advice.

## Stage 12d: found and fixed the likely actual root cause, not just the symptom

Stage 12c's fix made the diagnosis *safer* to give (verify before
blaming the network), but didn't explain *why* two independent people hit
this at all. Researched it (official Claude Code sandboxing docs,
`code.claude.com/docs/en/sandboxing`) rather than guessing, and found a
concrete, well-documented mechanism that fits both incidents:

- Claude Code's sandboxed Bash tool "pre-allows no domains by default";
  each new host a sandboxed command touches needs approval, and in auto
  mode that approval is scoped to a single command, not the session.
- An unapproved host is refused silently at the sandbox/proxy level --
  no prompt, no distinct signal reaching the Python process, just a
  connection failure indistinguishable from a real network problem.
- Grepped the skill's own source and confirmed it talks to **three
  different host patterns**: `www.wikidata.org`, `wikimedia.org`
  (pageviews REST API, no `www.`), and a *new* `<lang>.wikipedia.org`
  host per requested language (redirect resolution) --
  `scripts/wikitrends/wikidata.py:9,90` and
  `scripts/wikitrends/pageviews.py:10,128`.
- Stage 12c's `curl` verification command was **hardcoded to
  `www.wikidata.org` regardless of which URL actually failed** -- so if
  the real block was on `wikimedia.org` or a specific `xx.wikipedia.org`,
  the verification would give a false "all clear, just retry" when the
  host really was blocked and needed approving, not retrying. This also
  explains the original incident's pattern exactly: the user's own manual
  `curl`/`uv run` test ran *outside* Claude Code's Bash tool entirely (no
  sandbox at all), so of course it worked, while the agent's run of the
  identical command went through the sandboxed Bash tool and could hit an
  unapproved host.

Fixed:
- `http.py`'s `network_error` hint now curls the **exact URL that
  failed** (`get_json` already has it), not a fixed stand-in -- so the
  verification actually tests the host that matters.
- The hint also tells the agent to check the Bash tool's own result
  (separate from this script's error output) for a blocked/disallowed
  host message before concluding anything about the user's network --
  that signal means the fix is approving the host, not a network
  diagnosis.
- `SKILL.md`'s `compatibility` field and error table, `references/
  interpreting.md`, and `README.md`'s "Known limitations" now name all
  three host patterns explicitly and explain the sandbox-allowlist
  mechanism, so a future maintainer (or a differently-behaved agent) has
  the real explanation on hand instead of re-diagnosing from scratch.

Two new tests: the hint curls the specific failing URL for a
`pl.wikipedia.org` and a `wikimedia.org` failure (not just
`wikidata.org`), and the hint mentions checking for a sandbox
host-approval block. Full suite: 127 passed. `claude plugin validate .`:
clean.

This is the most likely explanation given the evidence (matches both
independent incidents precisely), not a confirmed root cause from either
affected user's own sandbox settings -- there was no way to get that
confirmation from a stranger who already moved on. The fix is safe either
way: it makes the diagnosis more accurate whether or not sandboxing is
the actual cause in a given case.

## Stage 12e: SKILL.md's frontmatter was actually invalid YAML

Prompted by a direct question -- "did we actually do everything the spec
requires?" -- re-checked against the spec's own tooling instead of
against our own tests, since our own tests are exactly what could share
a blind spot with the code they're checking.

The [Agent Skills spec](https://agentskills.io/specification) names a
reference validator: `skills-ref` (CLI: `agentskills validate`). Ran it
for the first time against this skill:

```
uvx --from skills-ref agentskills validate skills/wiki-interest-trends
```

**It failed.** `description`'s value was a bare, unquoted YAML plain
scalar containing "Ukrainian keywords for triggering: інтерес до теми,
...", and a colon-space sequence *inside* a plain scalar is invalid YAML
-- both `skills-ref` (which parses with `strictyaml`) and plain PyYAML
independently rejected it with the same parse error.

**Our own `test_skill_md.py` never caught this**, and that's the more
important finding: it read frontmatter with a hand-rolled per-line
`key: value` string split, which happily returned a `description` value
without ever attempting real YAML parsing. Every one of its checks
passed on a file the spec's own reference implementation would reject
outright -- a textbook case of a test suite sharing its author's blind
spot with the code, because both trusted the same lenient hand-rolled
parse instead of the real grammar. `claude plugin validate .` didn't
catch it either -- it validates the plugin/marketplace manifests, not
SKILL.md's own frontmatter, so it isn't a substitute for `skills-ref`.

Fixed:
- `description` rewritten as a YAML folded block scalar (`>-` across
  several indented lines) instead of one unquoted line. Verified by
  parsing the new frontmatter and asserting the round-tripped string is
  byte-for-byte identical to the original description -- this was a
  formatting change only, the actual text content didn't change.
- `skills-ref==0.1.1` added to `requirements.txt` (test-only).
- `test_skill_md.py` rewritten to parse frontmatter with `skills-ref`'s
  own `parse_frontmatter` (real YAML, not string-splitting), and a new
  `test_passes_the_official_agent_skills_reference_validator` runs
  `skills_ref.validate()` itself -- the actual authoritative check, not
  our interpretation of it.

`uvx --from skills-ref agentskills validate skills/wiki-interest-trends`
now prints `Valid skill: skills/wiki-interest-trends`. Full suite: 128
passed. `claude plugin validate .`: clean.

Answering the question this stage started from: yes, modulo this one
real defect, which is now fixed and now has a test that would have
caught it from the start. There's no remaining known gap against the
spec as of this commit -- but that claim is only as strong as the
checks that exist, which is exactly why this stage replaced a
hand-rolled check with the spec's own validator rather than just
patching the one YAML error and moving on.

## Stage 12f: a third, independent network_error misdiagnosis -- different product, different fix

A third real occurrence, reported directly by the maintainer from a
stranger's session: same symptom (`network_error` misdiagnosed as "your
organization's network policy blocks this"), but the transcript showed
the agent offering to "connect a folder from your Mac" to get a local
shell -- meaning this session had no local Bash tool at all. That's
claude.ai chat or Claude Desktop, not Claude Code, so Stage 12c/12d's
fix (curl the exact URL, then check the *Bash tool's* own result for a
blocked-host message) doesn't fully apply -- there's no Bash tool to
check the result of.

Researched claude.ai's own hosted code-execution sandbox specifically
(as opposed to Claude Code's local Bash sandbox, which is a completely
separate mechanism): it has its own network policy under Settings >
Capabilities > Code execution > Allow network egress, defaulting to
"package managers only" for Team/Enterprise accounts -- which doesn't
include any of this skill's hosts by design, with zero relation to the
company's actual firewall/VPN. Confirmed via Anthropic's own published
Team/Enterprise capability docs and multiple real, open GitHub issues
(anthropics/claude-code#93520, #38984, #51400) showing that even adding
domains to the allowlist there doesn't always reliably take effect.

So there are now three, not two, non-network explanations to rule out,
and **which one applies depends on which Claude product is running the
skill** -- something the agent always knows about itself, so the fix is
to have it use that knowledge instead of guessing:

1. Transient failure -- ruled out by curl on the exact URL succeeding.
2. Claude Code's Bash-tool sandbox hasn't approved this host (Stage
   12d) -- tell from the Bash tool's own result.
3. **New:** claude.ai chat/Claude Desktop's Capabilities network-egress
   setting doesn't include this host -- there's no Bash tool result to
   check here; the fix is the account/org owner adding the hosts under
   Capabilities, not IT, who have no access to that setting at all.

Fixed: `http.py`'s `network_error` hint, `SKILL.md`'s error table (now
short, pointing at the full decision tree rather than growing inline
again), and `references/interpreting.md`'s `network_error` section all
now cover all three causes explicitly, telling the agent to pick based
on which product it's running as. New test asserts the hint names the
Capabilities/network-egress setting specifically, not just a generic
"ask your admin." Full suite: 129 passed. Both validators (`claude
plugin validate .`, `agentskills validate`) clean.

As with Stage 12d, this is the most likely explanation given the
transcript's own evidence (the "connect a folder" offer only makes sense
without a local Bash tool), not a confirmation from that specific
stranger's account settings -- there was no way to get that
confirmation. The fix is safe regardless: it makes the agent name a
setting that actually exists and that someone can actually act on,
instead of "contact IT" for a setting IT has no access to.

## Stage 13: English + Ukrainian, not Ukrainian-first

Asked to make the skill work equally well for questions in English and
in Ukrainian. Researched how multilingual skills are done before
changing anything:

- The `description` is the only text an agent sees before deciding to
  load a skill. An English-only description *can* match other-language
  requests, but it isn't guaranteed. There's a real report of skills
  with English-only trigger phrases firing zero times in 45 days for a
  user who writes in Chinese (anthropics/claude-code#68086). The
  workaround is literal trigger phrases in each language, inside
  `description`. There is no `triggers` field; that issue is a feature
  request, and `skills-ref`'s `ALLOWED_FIELDS` confirms the spec has no
  such field.
- `SKILL.md` and references can stay in English (the agent reads them).
  What matters is telling the agent to answer in the user's language.
- Test triggering with real user phrases in each language, i.e. evals.

Audited the skill against that and found four real gaps, not just the
description:

1. **The PDF's chart was always English**, even in a `--lang uk` report.
   `report.py` embedded `analyze.py`'s `chart.png`, drawn with a
   hardcoded English title, y-axis label and "peak" markers, before the
   report's language is known. No test could see it, because `pypdf`
   can't read text inside an image. This is the same class of bug as
   Stage 6's English trust reasons in a Ukrainian report, one layer
   further down.
2. `report.py --lang` defaulted to `uk`.
3. `SKILL.md`'s examples and the PDF-offer line were Ukrainian only, and
   nothing explained that `analyze.py --lang` (a Wikipedia edition) and
   `report.py --lang` (the output language) mean different things.
4. All 8 eval scenarios were in Ukrainian; none was in English.

Fixed:
- New `wikitrends/i18n.py` (`SUPPORTED_LANGS`, `DEFAULT_LANG = "en"`,
  `pick()`): one fallback rule for all three string tables (report labels,
  chart labels, trust reasons). A parity test fails CI if any language is
  missing a key the other has. See `docs/dev/i18n.md`.
- `chart.py` takes `analysis.json`'s own `normalized` dicts, not
  `NormalizedPoint` objects, and has localized labels. That also removed
  the `normalized_points` duplicate `analyze.py` used to carry and strip
  before writing the JSON. It also keeps `chart.py` from importing
  `pageviews.py` → `requests`, which would have brought back Stage 6's
  `ModuleNotFoundError` in `report.py`'s PEP 723 environment.
- `report.py` redraws its own chart in `--lang` from `analysis.json` and
  embeds that, and skips the chart section when no series has data.
  `--lang` now defaults to `en`.
- `SKILL.md`: English and Ukrainian trigger phrases in `description` (995
  of 1024 chars, still valid YAML per `skills-ref`), a Language section
  that separates answer language / report language / analyzed edition,
  an English example, and the PDF offer in both languages.
- 3 English eval scenarios, including an English question about the
  Ukrainian edition (answer in English, but analyze `uk`).

**Verified live, not just in tests**, from an empty scratch directory
with each script's own PEP 723 dependencies only:
`resolve_topic.py --query astronomy --query-lang en` → Q333;
`analyze.py --qids Q333 --langs en,uk --last 24m` → real data (en −20%
YoY, uk −60%, both high trust); `report.py` run twice, `--lang en` and
`--lang uk`. Both PDFs are exactly one page, with text fully in the
requested language (checked via `pypdf`). The Ukrainian chart PNG was
opened and looked at directly: Ukrainian title, y-axis, and «пік» markers.
Full suite: 140 passed. `claude plugin validate .` and
`agentskills validate` both clean.

**Live agent evals** used the Stage 9 method: `claude --model haiku -p`,
with this branch's skill symlinked into a scratch workspace's
`.claude/skills/`. Each transcript's "Base directory for this skill"
confirmed the branch copy was the one loaded, not the older
globally-installed plugin.

- `english_single_topic_trust`, round 1: the skill triggered from a
  purely English question. It ran `--query-lang en --langs en` and gave
  the whole answer in English, with trust level and reasons. **Two
  failures:**
  1. No PDF offer at the end; the agent offered a different follow-up
     question instead. The offer instruction was buried inside Workflow
     step 4, which the agent skips when no report was asked for.
  2. It paraphrased "Trend direction holds after normalizing for the
     language edition's overall traffic" as "adjusting for the fact that
     English Wikipedia itself gets more traffic". That's an invented
     cause, and backwards: raw −20% vs. normalized −14% means the edition
     is *shrinking*.

  Fixed both with explicit rules in "How to write conclusions", the
  section Stage 9 showed Haiku reliably follows: the PDF offer is the
  last line of every answer that didn't produce a PDF; don't add causes
  the JSON doesn't state; and how to read the edition's own traffic
  direction from raw vs. normalized YoY.
- `english_single_topic_trust`, round 2, after the fix: it ended with
  "Want me to turn this into a one-page PDF report with a chart?", and
  the normalization reason was paraphrased neutrally ("after accounting
  for changes in overall English Wikipedia traffic").
- `english_compare_langs_report`: `resolve_topic.py --query-lang en
  --langs en,de,pl` → `analyze.py` → `report.py --lang en`, with
  `--question`/`--summary` in English. The PDF is one page, entirely in
  English, and the chart PNG is in English too (opened and looked at).
  It also correctly reported that Polish Wikipedia has no article.
- `single_topic_trust` (Ukrainian, regression check): answered in
  Ukrainian with trust level and reasons, ending with the Ukrainian PDF
  offer.

Not run: `english_question_about_ukrainian_edition`.
