# Dev plan — wiki-interest-trends

Internal working notes. Not part of the shipped skill (the skill itself is
`SKILL.md` + `scripts/` + `references/` + `assets/` + `tests/`). Kept here,
committed, so progress and decisions survive between sessions. The
reviewer-facing `README.md` gets written for real at Stage 10 — until then
it stays a stub.

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
(`scripts/wikitrends/`) instead of being copy-pasted per script, so a fix
(say, to backoff behavior) only happens once.

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
wiki-interest-trends/
├── SKILL.md
├── README.md                  # stub now, real deliverable at Stage 10
├── DEV_PLAN.md                 # this file — internal only
├── requirements.txt
├── scripts/
│   ├── resolve_topic.py        # CLI: topic/QID -> candidates -> per-language article titles
│   ├── analyze.py              # CLI: QIDs/titles + langs + range -> analysis.json + short stdout JSON
│   ├── report.py                # CLI: analysis.json -> 1-page PDF
│   └── wikitrends/              # shared library, no CLI code here
│       ├── __init__.py
│       ├── http.py              # requests session, UA, retry/backoff, 404-vs-error split
│       ├── cache.py             # SQLite cache keyed by (endpoint, params), TTL for current month
│       ├── wikidata.py          # wbsearchentities / wbgetentities / sitelinks helpers
│       ├── pageviews.py         # per-article / aggregate / redirects-of fetchers
│       ├── stats.py             # YoY, Theil-Sen + Mann-Kendall, peak share, seasonality
│       ├── trust.py             # deterministic high/medium/low rule + reasons
│       ├── chart.py             # matplotlib PNG rendering
│       ├── errors.py            # AppError -> {"ok": false, "error_code", "message", "hint"} contract
│       └── cli.py               # --help formatting, output-dir/run-id helpers shared by all 3 scripts
├── references/
│   ├── methodology.md
│   ├── api-notes.md
│   └── interpreting.md
├── assets/fonts/DejaVuSans*.ttf
├── evals/evals.json
├── VERIFICATION.md              # written at Stage 9
├── docs/dev/                    # internal-only: one short doc per feature/module
│   ├── http-client.md
│   ├── cache.md
│   ├── errors-and-cli-contract.md
│   └── wikidata-lookup-and-resolve-topic.md
└── tests/
    ├── fixtures/
    └── test_*.py
```

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
- [ ] **Stage 5 — `analyze.py` finished**: chart.py (PNG) + CLI wiring +
      `analysis.json` + compact stdout JSON contract. `--help` with
      examples.
- [ ] **Stage 6 — `report.py`**: 1-page PDF via reportlab + DejaVu fonts,
      summary passed in by the agent, limitations/trust level auto-filled.
      Test asserts page count == 1.
- [ ] **Stage 7 — `SKILL.md` + `references/`**: methodology.md,
      api-notes.md (formalized from Stage 0), interpreting.md.
- [ ] **Stage 8 — full offline test suite**: fixtures for all three
      scripts, 404/missing-language/ambiguous-topic/redirect cases, spot
      check 2-3 articles against pageviews.wmcloud.org.
- [ ] **Stage 9 — evals**: `evals/evals.json` (3 sample queries + edge
      cases from the spec), run for real on Haiku 4.5, fix `SKILL.md`/CLI
      contracts based on failures (not the eval), `VERIFICATION.md` log.
- [ ] **Stage 10 — final `README.md`** for the reviewer: install/run,
      architecture rationale, "як розвивати далі".
- [ ] **Stage 11 — real end-to-end run (I actually execute this, not just
      write tests for it)**: after everything above is green, run the
      finished skill for real, against the live network, the way the agent
      would:
      - `uv run scripts/resolve_topic.py ...` and `uv run
        scripts/analyze.py ...` and `uv run scripts/report.py ...` for
        real, for all 3 example queries from the task (§"Приклади
        запитів"), not fixtures — confirm the JSON contracts and the PDF
        actually come out right against today's live data.
      - Cross-check the numbers for 2-3 articles against
        https://pageviews.wmcloud.org by hand.
      - Run the real cache-hit path: repeat a query and confirm the second
        run does not hit the network (per the spec's "повторні запити мають
        бути швидкими завдяки кешу").
      - Run the full `evals/evals.json` suite for real on Haiku 4.5 (e.g.
        `claude --model haiku`), not a simulated/predicted transcript —
        record call counts and failures, fix `SKILL.md`/script contracts
        (not the eval) based on what actually happens.
      - Write up everything actually observed (commands run, output,
        fixes made) in `VERIFICATION.md` — this is the log the reviewer
        checks to know the AI's own claims were verified, not asserted.

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
