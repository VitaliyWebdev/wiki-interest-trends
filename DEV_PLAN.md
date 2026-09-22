# Dev plan — wiki-interest-trends

Internal working notes. Not part of the shipped skill (the skill itself,
since Stage 12, is `skills/wiki-interest-trends/` containing `SKILL.md` +
`scripts/` + `references/` + `assets/` — see "Why `skills/wiki-interest-trends/`"
below). Kept here, committed, so progress and decisions survive between
sessions.

**Rule:** alongside this stage checklist, every feature/module gets its own
short doc in `docs/dev/` right after it's built and tested — what it's for,
its contract, and non-obvious decisions/gotchas. This file tracks *progress*;
`docs/dev/*.md` is what actually saves a future session from re-reading all
the code. `docs/dev/` is internal-only, distinct from `references/` (the
shipped, agent-facing docs bundled into the skill itself).

## Goal

Agent Skill that lets a Haiku-4.5-driven agent answer "is interest in topic
X growing, in which language editions, how confident should we be" using
Wikipedia pageviews, and optionally produce a 1-page PDF report.

## Why the architecture is shaped this way

All logic (HTTP, caching, stats, trust scoring, plotting, PDF) lives in
Python that runs via `uv run` — **not** in the agent's reasoning. Haiku only
calls 2-3 scripts with simple flags and reads short JSON. So the correctness
bar for the Python is much higher than for a typical internal script: it's
covered by tests against recorded fixtures, not by the agent noticing when
numbers look wrong.

Reusability requirement: `resolve_topic.py`, `analyze.py`, `report.py` all
need the same HTTP client (retries, User-Agent, 404-vs-error distinction),
the same cache, and the same "small JSON to stdout, everything else to a
file" contract. That shared behavior lives in one package
(`skills/wiki-interest-trends/scripts/wikitrends/`) instead of being
copy-pasted per script, so a fix (say, to backoff behavior) only happens
once.

## Stage 0 — API research (done)

Real requests made against production endpoints (not from memory):

- `wbsearchentities` (wikidata.org) — search by label in any language,
  returns candidates with id/label/description. Confirmed via "інтервальне
  голодування" → `Q1666254`.
- `wbgetentities` with `props=sitelinks` — a language with no article simply
  has **no key** for that wiki (e.g. no `plwiki` key at all) — there is no
  explicit "missing" flag from the API, we synthesize one.
- Per-article pageviews
  (`/metrics/pageviews/per-article/{project}/all-access/user/{article}/{granularity}/{start}/{end}`)
  — works, returns real monthly counts. Article title must be
  space→underscore then percent-encoded; passing raw UTF-8 with a literal
  space produces a `400 Invalid HTTP Request` from the edge, not a clean
  error.
- No data / no such article → **404 with a JSON body**
  (`{"status":404,"title":"Not Found",...}`), not a network-level failure —
  must be handled as a normal "no data" case per (article, language) pair,
  not raised as an error.
- Aggregate pageviews
  (`/metrics/pageviews/aggregate/{project}/all-access/user/{granularity}/{start}/{end}`)
  — works, gives project-wide totals for normalization.
- Redirect resolution: MediaWiki `action=query&redirects` resolves a title
  to its canonical form. Reverse lookup (`prop=redirects`) lists the
  redirects pointing at a canonical title, for `--include-redirects`; it
  paginates (`rdcontinue`) for popular articles with many redirects.
- No explicit rate-limit headers observed; responses do carry
  `cache-control: s-maxage=14400` (4h) from Wikimedia's own edge. No
  429/5xx seen during testing — backoff logic will be written defensively
  per the task spec (exponential backoff, since we can't rely on
  `Retry-After` being present) rather than tuned against an observed case.

Full writeup with example requests/responses goes in
`references/api-notes.md` at Stage 7 — this section is the working notes
version.

## File structure

```
wiki-interest-trends/                 # repo root = dev workspace + plugin root
├── .claude-plugin/
│   ├── plugin.json                   # Stage 12: makes this repo a Claude Code plugin
│   └── marketplace.json              # Stage 12: self-hosted single-plugin marketplace
├── LICENSE                           # MIT (Stage 12)
├── SKILL.md                          # -> moved under skills/wiki-interest-trends/ (Stage 12)
├── README.md                         # reviewer-facing, written at Stage 10
├── DEV_PLAN.md                       # this file — internal only
├── VERIFICATION.md                   # written at Stage 9, extended at Stage 12
├── requirements.txt
├── conftest.py                       # points pytest at skills/wiki-interest-trends/scripts
├── evals/evals.json
├── docs/dev/                         # internal-only: one short doc per feature/module
│   ├── http-client.md
│   ├── cache.md
│   ├── errors-and-cli-contract.md
│   ├── wikidata-lookup-and-resolve-topic.md
│   ├── pageviews.md
│   ├── stats-and-trust.md
│   ├── chart-and-analyze-cli.md
│   └── report-pdf.md
├── tests/                            # stays at repo root -- dev-only, like docs/dev/
│   ├── fixtures/
│   └── test_*.py
└── skills/
    └── wiki-interest-trends/         # <- the actual Agent-Skills-spec skill directory
        ├── SKILL.md
        ├── scripts/
        │   ├── resolve_topic.py      # CLI: topic/QID -> candidates -> per-language article titles
        │   ├── analyze.py            # CLI: QIDs/titles + langs + range -> analysis.json + short stdout JSON
        │   ├── report.py             # CLI: analysis.json -> 1-page PDF
        │   └── wikitrends/           # shared library, no CLI code here
        │       ├── __init__.py
        │       ├── http.py          # requests session, UA, retry/backoff, 404-vs-error split
        │       ├── cache.py         # SQLite cache keyed by (endpoint, params), TTL for current month
        │       ├── wikidata.py      # wbsearchentities / wbgetentities / sitelinks helpers
        │       ├── pageviews.py     # per-article / aggregate / redirects-of fetchers
        │       ├── stats.py         # YoY, Theil-Sen + Mann-Kendall, peak share, seasonality
        │       ├── trust.py         # deterministic high/medium/low rule + reasons
        │       ├── chart.py         # matplotlib PNG rendering
        │       ├── errors.py        # AppError -> {"ok": false, "error_code", "message", "hint"} contract
        │       └── cli.py           # --help formatting, output-dir/run-id helpers shared by all 3 scripts
        ├── references/
        │   ├── methodology.md
        │   ├── api-notes.md
        │   └── interpreting.md
        └── assets/fonts/DejaVuSans*.ttf
```

**Why `skills/wiki-interest-trends/` and not the repo root, post-Stage-11:**
Stage 12 (below) converts this repo into an installable Claude Code
*plugin*, which expects its bundled skill(s) under `<plugin-root>/skills/<skill-name>/`.
`docs/dev/`, `tests/`, `DEV_PLAN.md`, `VERIFICATION.md`, `evals/` stay at
the repo root — same reasoning as always: they're dev/verification
tooling, not part of what an agent reads to use the skill. Every internal
path reference (tests' `sys.path`, docs' `**File:**` headers, README's
commands) was updated accordingly; see the Stage 12 entry for the full
list of what moved and why.

Rationale for the split inside `wikitrends/`: each file owns exactly one
concern (HTTP transport vs. caching vs. domain lookups vs. stats vs.
presentation) so a bug in, say, the trust rule can be fixed and tested
without touching HTTP or caching code, and `analyze.py` and
`resolve_topic.py` both reuse `http.py`/`cache.py`/`wikidata.py` instead of
duplicating request logic.

## Stages

Each stage ends in a working, independently-testable piece, committed and
pushed. We check in after each one before moving on — no stage starts
without a green light on the previous one.

- [x] **Stage 0 — API research** (above)
- [x] **Stage 1 — `wikitrends` plumbing**: `http.py` (UA, retry/backoff,
      404 split), `cache.py` (SQLite, short TTL for current incomplete
      month), `errors.py` (error-JSON contract). Unit tests with a fake
      transport (no real network in tests). 23 tests, all green. TDD
      throughout (each module: write tests, watch fail, implement, watch
      pass). Note: TTL policy (short TTL for the current incomplete month,
      permanent for closed months) is a *caller* decision — `cache.py`
      only provides `ttl_seconds=None` (forever) vs. a number; `pageviews.py`
      in Stage 3 decides which to pass per month.
- [x] **Stage 2 — `resolve_topic.py`**: `wikidata.py` (search, sitelinks,
      redirects, all cached, 7-day TTL) + `cli.py` (shared stdout/error
      contract) + the CLI itself. Never silently picks a candidate — always
      returns every match with description, so ambiguous topics (tested
      against the real "Меркурій" case: planet/element/god/city/ship) get
      surfaced, not guessed. 38 tests total, all against real recorded
      fixtures, no live calls in the test suite. Smoke-tested for real via
      `uv run scripts/resolve_topic.py` against live Wikidata (not just
      fixtures) before committing.
- [x] **Stage 3 — pageviews fetching**: `pageviews.py` (per-article,
      aggregate, redirects-of, title encoding, 404 handling, normalization).
      13 new tests (64 total), all against real recorded fixtures. Two real
      gotchas confirmed against the live API and documented in
      `docs/dev/pageviews.md`: unescaped `/` in a title → false "no data"
      404; monthly granularity gives a *partial* sum for the last month
      unless `end` is that month's actual last day. Note: this stage built
      `pageviews.py` itself only, not `analyze.py` — the CLI file and the
      `--include-redirects` summation logic are Stage 5 (chart+CLI wiring),
      so `analyze.py` doesn't exist as a file yet. Smoke-tested live via a
      throwaway script against real Wikidata/Wikimedia before committing.
- [x] **Stage 4 — stats + trust**: `stats.py` (YoY, Theil-Sen/log,
      Mann-Kendall, peak concentration, seasonality) and `trust.py`
      (deterministic high/medium/low + human-readable reasons). 28 new
      tests (79 total), all against synthetic series with a mathematically
      known correct answer (e.g. Theil-Sen recovers exact ln(2) even with a
      1,000,000-view outlier injected; Mann-Kendall S/p cross-checked
      against an independently written reference calc, not just re-run
      through the same code). No network involved in this stage at all —
      pure math.
- [x] **Stage 5 — `analyze.py` finished**: `chart.py` (PNG, peaks marked) +
      CLI wiring + `analysis.json` + compact stdout JSON contract, `--help`
      with examples. `--qids`+`--langs` (cross-language, via Wikidata) and
      `--titles`+`--lang` (single-language, direct, for fast repeat
      queries) both supported. `--last Nm` resolves to N *complete*
      calendar months ending at the most recent finished month specifically
      to avoid the Stage-3 partial-month trap. 21 new tests (100 total).
      Smoke-tested live via `uv run` from an external cwd (not the skill
      directory) against real Wikimedia before committing.
- [x] **Stage 6 — `report.py`**: 1-page PDF via reportlab + DejaVu fonts
      (copied from matplotlib's own bundle), summary passed in by the
      agent, limitations/trust level auto-filled and localized (uk/en).
      Raw Canvas API so single-page is structural, not hopeful. 25 new
      tests (116 total). Found and fixed 2 real bugs only visible by
      actually running the script and looking at the rendered PDF: a
      missing transitive `requests` dependency (report.py never makes an
      HTTP call but imported a module that did), and trust reasons being
      hardcoded English inside an otherwise-Ukrainian report (fixed by
      making `trust.Reason` code+params with uk/en render templates).
- [x] **Stage 7 — `SKILL.md` + `references/`**: methodology.md,
      api-notes.md (formalized from Stage 0/3), interpreting.md.
      Frontmatter verified against the live `agentskills.io/specification`
      (fetched, not recalled from training) -- name/description/
      compatibility constraints, 165-line body (well under the ~300 target).
      `tests/test_skill_md.py` added as an automated stand-in for
      `skills-ref validate`.
- [x] **Stage 8 — full offline test suite**: fixtures for all three
      scripts, 404/missing-language/ambiguous-topic/redirect cases (mostly
      landed incrementally in Stages 2/3/5; filled the one real gap found —
      `--include-redirects` summation in `analyze.py` had no direct test).
      124 tests total. Spot-checked 2 articles + 1 project total against
      pageviews.wmcloud.org live in the browser — all three exact matches,
      logged in `VERIFICATION.md`.
- [x] **Stage 9 — evals**: `evals/evals.json` (3 sample queries + 5 edge
      cases). All 8 run for real on `claude --model haiku`, against the
      skill symlinked into a scratch workspace as a real discoverable
      project skill. Found and fixed 3 real `SKILL.md` gaps (relative
      script paths breaking outside the skill dir — and a first fix that
      was itself wrong, caught by re-running, not just reasoning about it;
      unspecified-languages treated like genuine topic ambiguity; "звіт"
      not triggering `report.py`). Full before/after log in
      `VERIFICATION.md`.
- [x] **Stage 10 — final `README.md`** for the reviewer: install/run, the
      3 primary examples, architecture rationale, known limitations, and
      "як розвивати далі" (scale, deeper research, other signal sources).
- [x] **Stage 11 — real end-to-end run**: all 3 scripts run for real via
      `uv run` (repeatedly through Stages 2/3/5/6, and again for all 3
      primary example queries via real Haiku transcripts in Stage 9).
      Numbers cross-checked against pageviews.wmcloud.org (Stage 8).
      Cache-hit path confirmed live and decisively: 3 repeat runs against
      a fresh cache dir, `cache.sqlite3`'s mtime/size byte-identical after
      the 2nd and 3rd runs (zero writes = zero misses = zero network
      calls). Full eval suite run for real on Haiku 4.5 (Stage 9).
      Everything logged in `VERIFICATION.md`.

**All 11 planned stages complete.** The skill is built, tested (124 tests),
documented (`SKILL.md` + `references/` + `docs/dev/`), verified against
live data and a live Haiku 4.5 run, with every finding from that
verification fixed in the skill itself rather than worked around.

- [x] **Stage 12 (post-completion) — Claude Code plugin + self-hosted
      marketplace**, so any user (not just developers comfortable with
      git) can add this skill with two slash commands instead of a manual
      clone/symlink. Schema verified against the live docs (fetched
      `plugins-reference.md` / `plugin-marketplaces.md` directly, not
      recalled) before writing `.claude-plugin/plugin.json` /
      `.claude-plugin/marketplace.json` — the self-referential
      `"source": "./"` case for a single-plugin-at-repo-root marketplace
      isn't spelled out with a worked example in the docs, so this was
      confirmed by fetching the docs' own text on relative-path resolution
      rather than guessed. Required moving `SKILL.md`/`scripts/`/
      `references/`/`assets/` into `skills/wiki-interest-trends/` per
      plugin convention (`<plugin-root>/skills/<skill-name>/SKILL.md`) --
      `tests/`/`docs/dev/`/`DEV_PLAN.md`/`VERIFICATION.md`/`evals/` stay at
      the repo root, same "not part of the shipped skill" reasoning as
      always. Every internal path reference updated: `conftest.py`, the 3
      test files with their own `sys.path.insert`, `test_skill_md.py`'s
      `SKILL_MD` constant, README's commands and links, and every
      `**File:**`/prose path mention across `docs/dev/*.md`. Added
      `LICENSE` (MIT) — flagged as missing back in Stage 10's README, now
      actually needed since this makes the skill genuinely
      publicly-installable. Done on a branch
      (`plugin-marketplace-restructure`), merged to `main` once verified
      — see `VERIFICATION.md` for the real `/plugin marketplace add` +
      `/plugin install` test.

## Global constraints (from the spec, copied verbatim in spirit)

- Python 3.10+, PEP 723 inline script metadata, run via `uv run
  scripts/<name>.py`; `requirements.txt` kept in sync for plain `pip`.
- No compiled binaries; everything lives inside the skill directory.
- Scripts write outputs to `./wikitrends-out/<run-id>/` in the *caller's*
  cwd, never inside the skill directory.
- Cache: SQLite under `~/.cache/wikitrends/` (override via
  `WIKITRENDS_CACHE`).
- stdout is compact JSON only (~40 lines), errors are
  `{"ok": false, "error_code", "message", "hint"}`.
- `WIKITRENDS_CONTACT` env var feeds the User-Agent contact info.
- All user-facing report text and `SKILL.md` body prose: per spec section
  on language (report in user's language; `SKILL.md` body in English;
  description carries Ukrainian keywords too).
