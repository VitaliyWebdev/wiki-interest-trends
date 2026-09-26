# wiki-interest-trends

An [Agent Skill](https://agentskills.io/specification) that lets an AI
agent (designed for cheap/fast models like Claude Haiku 4.5) research
topic interest via Wikipedia pageviews across language editions: growth,
trend significance, a deterministic confidence level, and an optional
one-page PDF report — for B2C product founders deciding what to build or
where to localize.

Works the same for questions asked in **English, Ukrainian, Polish or
Czech**. The skill triggers on phrases in each of them. The agent answers
in the user's language, and the PDF (headings, table values, trust
reasons, and the chart itself) is rendered in that language via
`report.py --lang en|uk|pl|cs`. Article titles in any script, including
Chinese, Japanese and Korean, print correctly in the chart and the PDF.
The language of the answer is independent of which Wikipedia editions get
analyzed, so an English question about the Ukrainian edition works fine.
See [`docs/dev/i18n.md`](docs/dev/i18n.md) for how the localization is
structured and how to add another language.

The PDF reads top-down like an executive one-pager: the question as the
headline, the agent's conclusion, KPI cards (YoY per series, overall
trust), a vector chart with labeled lines, a per-series table with
sparklines, and the reasons behind the trust level. See
[`docs/dev/report-design.md`](docs/dev/report-design.md) for why each
piece looks the way it does.

All statistics run in tested Python, not in the agent's own reasoning —
see [Why the architecture is this shape](#why-the-architecture-is-this-shape).

## Install & run

Requires [uv](https://docs.astral.sh/uv/) — that's it. You do **not** need
Python pre-installed separately: every script declares its required
version via [PEP 723](https://peps.python.org/pep-0723/) inline metadata,
and `uv run` downloads and manages a matching interpreter on its own the
first time it's needed. If `uv` itself isn't installed, the skill installs
it automatically when used through an agent (see `SKILL.md`'s "Step 0") —
or install it yourself once, no admin rights needed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
```

```bash
git clone https://github.com/VitaliyWebdev/wiki-interest-trends.git
cd wiki-interest-trends

# Find a topic's Wikidata QID and its article title per language
uv run skills/wiki-interest-trends/scripts/resolve_topic.py --query "інтервальне голодування" --query-lang uk --langs pl,cs

# Analyze growth/trend/trust across languages, over the last 24 complete months
uv run skills/wiki-interest-trends/scripts/analyze.py --qids Q1666254 --langs pl,cs,uk --last 24m

# Turn that into a one-page PDF (path comes from analyze.py's own output)
uv run skills/wiki-interest-trends/scripts/report.py --analysis-json wikitrends-out/<run-id>/analysis.json --lang uk \
  --summary "Your conclusion, grounded in the numbers above."
```

(These paths are repo-root-relative, for running the scripts directly from a
checkout. Inside `SKILL.md` itself, the same commands are written as
`scripts/resolve_topic.py` etc. — relative to the skill's *own* directory,
which is what an agent actually uses.)

Each script is self-contained via [PEP 723](https://peps.python.org/pep-0723/)
inline metadata — `uv run` handles the venv and pinned dependencies with no
setup step. `skills/wiki-interest-trends/requirements.txt` is kept in sync
for a plain `pip install -r requirements.txt` fallback (it lives inside the
skill directory itself, alongside `tests/` — both are part of the
self-contained skill per the [Agent Skills spec](https://agentskills.io/specification),
not just repo-level dev scaffolding). No compiled binaries are vendored;
the only non-code assets are two DejaVu Sans `.ttf` files (for
Cyrillic-capable PDF text) copied from matplotlib's own bundle.

Run the test suite (164 tests, no network required — all fixtures are
recorded real API responses). A `pytest.ini` at the repo root points
`pytest` at the tests' real location so this works from either place:

```bash
uv venv .venv && uv pip install -r skills/wiki-interest-trends/requirements.txt --python .venv/bin/python
.venv/bin/pytest                                   # from the repo root
cd skills/wiki-interest-trends && ../../.venv/bin/pytest   # or from inside the skill itself
```

### Installing as a Claude Code skill

**Recommended — as a plugin, via two terminal commands.** This repo is
its own self-hosted plugin marketplace (`.claude-plugin/marketplace.json` +
`.claude-plugin/plugin.json`). From an actual terminal (not the Claude
Code chat box — see the note below):

```bash
claude plugin marketplace add VitaliyWebdev/wiki-interest-trends
claude plugin install wiki-interest-trends@wiki-interest-trends-marketplace
```

Both commands complete in seconds and the skill becomes usable in every
Claude Code session immediately (project, desktop app, etc. — installed
at "user" scope). Run `/skills` in a session afterward to confirm it's
active. This exact flow was verified end-to-end in a completely fresh
scratch workspace with no prior setup at all — see `VERIFICATION.md`.

> **Why not just click a button in the desktop app?** Its "+" → Plugins
> → "Add marketplace" dialog *should* be able to do this with no
> terminal at all, but as of this writing it reliably fails with a
> generic "Failed to add marketplace" error for any custom/self-hosted
> marketplace (not specific to this repo) — the dialog's git clone
> prefers SSH and hangs with no usable credentials in that context,
> timing out after ~60s
> ([anthropics/claude-code#77927](https://github.com/anthropics/claude-code/issues/77927),
> closed as "not planned"). Separately, even a marketplace registered
> successfully via the CLI doesn't reliably show up when searching the
> desktop app's "Discover" tab
> ([anthropics/claude-code#43745](https://github.com/anthropics/claude-code/issues/43745)).
> Both are known, reported bugs in Claude Code itself — nothing to fix on
> this repo's side (`claude plugin validate .` passes clean). Once
> installed via the two commands above, the plugin works completely
> normally and shows up correctly under the desktop app's "Yours" tab.
>
> Typing `/plugin marketplace add ...` directly into the Claude Code chat
> box doesn't work either — it gets interpreted as "invoke a skill named
> `plugin`" rather than the CLI's slash command. The two `claude plugin
> ...` commands above are real shell commands, run from your terminal.

**Alternative — manual clone/symlink**, if you'd rather manage it as a
plain directory (e.g. to track your own fork without going through the
plugin system). Note the skill itself lives under `skills/wiki-interest-trends/`
in this repo, not at the repo root, so point Claude Code at that
subdirectory specifically:

```bash
# Personal — available in every project on this machine
git clone https://github.com/VitaliyWebdev/wiki-interest-trends.git /tmp/wit-src
ln -s /tmp/wit-src/skills/wiki-interest-trends ~/.claude/skills/wiki-interest-trends

# Or, if you already have a local checkout (e.g. this one, for development):
ln -s /path/to/your/wiki-interest-trends/skills/wiki-interest-trends ~/.claude/skills/wiki-interest-trends
```

Either way, `uv` still needs to be available locally (or the agent
installs it on first use, per `SKILL.md`'s Step 0) — neither install
method installs it for you; they only place the skill's files where
Claude Code looks for them. Python itself is never a separate
requirement, either way (see above).

## Examples

See [SKILL.md](skills/wiki-interest-trends/SKILL.md#examples) for the three primary example queries
this skill is designed around (cross-language comparison, single-topic
trust check, cross-topic comparison + report), each with the exact
commands an agent runs.

## Why the architecture is this shape

The whole point: Haiku calls 2-3 scripts with simple flags and reads a
short JSON summary. It never computes a percentage, a p-value, or a trust
level itself. That single decision drives everything else:

- **Correctness lives in tested Python, not agent reasoning.** 124 tests,
  most against real recorded API fixtures (not hand-written mocks), plus
  synthetic series with *mathematically known* correct answers for the
  statistics (e.g. Theil-Sen recovers an exact `ln(2)` slope even with a
  1,000,000-view outlier injected — see
  [docs/dev/stats-and-trust.md](docs/dev/stats-and-trust.md)).
- **One shared library, `skills/wiki-interest-trends/scripts/wikitrends/`**, not three copies of HTTP/
  cache/error-handling logic — `resolve_topic.py`, `analyze.py`, and
  `report.py` each stay a thin CLI layer over it. See
  [DEV_PLAN.md](DEV_PLAN.md)'s file structure section for the module
  breakdown and rationale.
- **The trust level is a deterministic rule in code** (concern-count over
  5 named factors: history length, view volume, trend significance,
  raw-vs-normalized agreement, peak concentration), never a judgment call
  handed to the calling model. Every level comes with human-readable
  reasons, localized to the report's own language — not just a bare label.
  Full rule: [references/methodology.md](skills/wiki-interest-trends/references/methodology.md).
- **Real API research over documentation-from-memory**, throughout. Two
  concrete gotchas that only showed up in actual requests, not the docs:
  an unescaped `/` in an article title causes a 404 that looks exactly
  like "no data" but means the URL is malformed; monthly-granularity
  pageviews return a *partial* sum for a month `end` falls mid-way
  through, not the full month. Both documented with the real requests that
  found them in [references/api-notes.md](skills/wiki-interest-trends/references/api-notes.md).
- **Every stage was verified by actually running it**, not just passing
  its own tests — live smoke tests via `uv run` after each stage, a
  rendered PDF actually looked at (which is how two real bugs were caught
  that every unit test missed — see
  [docs/dev/report-pdf.md](docs/dev/report-pdf.md)), numbers spot-checked
  against the independent [pageviews.wmcloud.org](https://pageviews.wmcloud.org)
  tool, and all 8 eval scenarios run for real against `claude --model
  haiku` in a scratch workspace with this skill installed as an actual
  discoverable project skill. Full log: [VERIFICATION.md](VERIFICATION.md).

`docs/dev/*.md` has one focused write-up per module (what it's for, its
contract, the non-obvious decisions and gotchas found building it) —
that's the fastest way into the actual implementation reasoning;
`DEV_PLAN.md` is the stage-by-stage build log this was developed against.

## Known limitations

- **The PDF's own labels come in four languages** (`en`, `uk`, `pl`,
  `cs`); any other `--lang` falls back to English labels, while the
  question, summary and article titles still print in their own language.
  Adding one is a translation job the parity test checks: see
  `docs/dev/i18n.md`.
- **Scripts that need shaping (Devanagari, Thai, Arabic joining) are not
  shaped**: neither matplotlib nor reportlab does complex text layout, so
  such titles print as separate, unjoined letters. Latin, Cyrillic, Greek
  and Chinese/Japanese/Korean are fine (CJK via bundled Droid Sans
  Fallback and NanumGothic, see `docs/dev/fonts.md`).
- **Year-over-year growth and seasonality only compute at monthly
  granularity** (`--granularity daily` gets trend/peak-share numbers but
  not those two) — both assume one data point per calendar month.
- **Trust-level thresholds** (30/100 views-per-month, 0.35/0.5 peak
  share, etc.) are reasoned defaults, not calibrated against a labeled
  dataset — none exists for this task. Real usage is the place to
  sanity-check them; they're named constants in
  `skills/wiki-interest-trends/scripts/wikitrends/trust.py`.
- **`--titles` mode is single-language by design** (compare several
  topics within one edition); cross-language comparison always goes
  through `--qids`. See `docs/dev/chart-and-analyze-cli.md` for the
  reasoning and when to revisit it.
- **Whatever sandbox is running the skill's scripts can silently block
  one of its hosts without a real network problem existing — and which
  sandbox it is depends on which Claude product is running the skill.**
  The skill talks to three different host patterns — `www.wikidata.org`,
  `wikimedia.org`, and a `*.wikipedia.org` host per requested language.
  In **Claude Code**, the local Bash-tool sandbox pre-allows no domains
  by default, approving them per command, so a host it hasn't approved
  yet fails exactly like a real network error. In **claude.ai chat or
  Claude Desktop** (no local Bash tool — code runs in Anthropic's own
  hosted sandbox), it's a separate setting entirely — Capabilities > Code
  execution > Allow network egress, defaulting to "package managers only"
  for Team/Enterprise accounts, which doesn't include any of these hosts
  by design. This has happened three times in real usage so far, each
  time misdiagnosed by the agent as "the user's organization blocks
  this" and pointing the user at IT, who control neither setting.
  `network_error`'s `hint` now curls the *exact* URL that failed (not a
  fixed stand-in) and tells the agent to triage by which product it's
  running as before saying anything about the user's network — see
  `references/interpreting.md`'s `network_error` section for the full
  decision tree. There's no code-side fix for either sandbox's denial
  itself: for Claude Code, pre-approve the hosts (e.g. via
  `sandbox.network.allowedDomains`); for claude.ai/Claude Desktop, the
  account or org owner adds them under Capabilities, though that setting
  is known to sometimes not take effect immediately even when configured
  correctly.

## How to develop further

**Larger scale.** The per-request REST API is fine for a handful of
topics/languages per query but doesn't scale to, say, "scan the top 500
articles of every language edition." For that: switch to Wikimedia's bulk
[pageview dumps](https://dumps.wikimedia.org/other/pageviews/) instead of
per-article API calls, parallelize fetches (currently sequential — fine at
this volume, a bottleneck at high volume), and move the cache from SQLite
to Parquet files queried with DuckDB once a single run's data stops fitting
comfortably in a key-value cache.

**Deeper research.** Right now each topic is one Wikidata QID and its
per-language sitelinks. Wikidata's link graph and category structure could
cluster *related* articles automatically (e.g. everything linked to/from a
topic, or sharing its categories) to discover adjacent topics worth
checking, instead of the agent having to name each one. The trend
detection (Theil-Sen + Mann-Kendall) is solid for "is there a trend" but
doesn't decompose seasonality from trend explicitly — an STL decomposition
would let the report separate "this always spikes every December" from
the actual underlying trend line, rather than just flagging
`seasonality_ratio` as a caveat. Actual forecasting (even a simple one)
would turn "is it growing" into "where might it be in 6 months," with
appropriately wide uncertainty given how noisy this signal already is.
`topviews`-style "what are the top articles in this language edition
right now" could seed new topic ideas rather than requiring the founder to
already have one in mind.

**Other signal sources.** Wikipedia pageviews are one interest signal
among many — Google Trends, App Store/Play Store category rankings,
Reddit/forum mention volume, or job-posting keyword frequency would each
add a different, differently-biased view of the same underlying question,
and cross-referencing them would catch cases where Wikipedia's audience
(people who read encyclopedic articles) doesn't represent the actual
target market well.

## Updating

Users don't need to re-clone or re-add anything — Claude Code pulls from
this GitHub repo itself. There's a background check, or a user can force
it immediately:
```bash
claude plugin update wiki-interest-trends@wiki-interest-trends-marketplace
# or, to refresh the whole marketplace:
claude plugin marketplace update
```

**Maintainer note — `.claude-plugin/plugin.json` intentionally has no
`version` field.** Per Claude Code's own docs: when `version` *is* set,
that exact string is the only update signal — push new commits without
bumping it, and every already-installed user keeps the stale cached copy
forever, even if they explicitly run an update command. Omitting `version`
makes Claude Code fall back to the resolved git commit SHA instead, so
every push to `main` is automatically a detectable update with nothing to
remember. Don't add a hardcoded `version` back without also committing to
bumping it on every single release.

Code: [MIT](LICENSE). `skills/wiki-interest-trends/assets/fonts/LICENSE.txt`
carries the DejaVu Sans font license (Bitstream Vera Fonts Copyright + Arev
Fonts Copyright, both permissive), extracted from the font's own embedded
metadata.
