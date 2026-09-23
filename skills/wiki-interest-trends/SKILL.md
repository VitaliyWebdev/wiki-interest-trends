---
name: wiki-interest-trends
description: >-
  Analyzes interest in a topic over time using Wikipedia pageview statistics
  across language editions -- compares growth, trend significance, and a
  confidence ("trust") level between languages or topics, and can produce a
  one-page PDF report with a chart. Use when researching audience/market
  interest for a product idea, deciding which languages or countries to
  localize or launch into, checking whether interest in a topic is growing
  or declining, comparing topic popularity across language editions, or
  preparing a founder/stakeholder-facing report backed by real data. Not for
  measuring purchase intent, ad-hoc trivia lookups, or
  real-time/breaking-news monitoring. Ukrainian keywords for triggering:
  інтерес до теми, тренди Wikipedia, чи росте попит, вибір мов для
  локалізації, порівняння ринків, аналіз популярності, перегляди статей,
  довіра до тренду.
compatibility: Requires uv (auto-installed by this skill if missing; uv manages its own Python, no separate Python install needed) and network access to www.wikidata.org, wikimedia.org, and a *.wikipedia.org host per requested language (e.g. en.wikipedia.org, uk.wikipedia.org).
metadata:
  version: "1.0"
---

# wiki-interest-trends

Wikipedia pageviews are a real, measurable signal of public interest and
awareness in a topic, in a specific language/region, over time. This skill
turns that signal into growth numbers, a trend significance test, a
deterministic confidence level, and (optionally) a one-page PDF a founder
can hand to someone else.

**All the statistics live in the Python scripts below, not in your own
reasoning.** Call the scripts, read their JSON, and build your answer from
the numbers they give you -- do not estimate a growth percentage, invent a
trend, or compute your own confidence level. That is the entire point of
this skill's design.

**Never conclude the scripts can't reach the network without actually
running them in *this* attempt.** If an earlier turn in this same
conversation hit a network error, that does not mean the same command
will fail again now -- sandbox approvals, admin settings, and transient
issues can all change between turns. Real incident: an agent recalled an
earlier failure from earlier in the conversation and told the user "this
environment has no access," without trying again, going straight to a
manual CSV workaround -- when simply re-running the command might have
worked. Re-attempt before repeating any network-related conclusion from
earlier in the conversation, every single time, no exceptions.

## When to use this skill

- "Is interest in X growing?" / "Чи росте інтерес до X?"
- Comparing a topic's popularity across language editions (which market to
  prioritize, which language to localize into)
- Comparing several topics within one language (which of these ideas has
  more existing awareness)
- Backing up a product/roadmap decision with a real trend chart, not a gut feeling

## When NOT to use it

- **Wikipedia pageviews measure interest/awareness, not willingness to
  pay.** Never phrase a conclusion as "there is demand for X" or "X will
  sell" -- say "interest in X is growing/declining/flat", full stop.
- Not for real-time or breaking-news monitoring -- data is typically
  monthly-granularity and lags by days.
- Not useful for a topic with no Wikipedia article in any relevant
  language -- there is nothing to measure.
- A single data point or a very short history isn't a trend -- the trust
  level will say so; don't override it with your own judgment.

## Workflow

**Step 0 — make sure `uv` is available** (`command -v uv`). If it isn't,
install it yourself before anything else -- this is a normal, user-scoped
install (no admin/root, writes only to `~/.local/bin`, never touches any
system Python), not something to ask the user to do by hand:
```
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```
If `uv` still isn't on `PATH` right after installing (new shells pick it
up automatically, the current one might not), call it as `~/.local/bin/uv`
for the rest of this session. **Python itself never needs separate
installation** -- every script below declares its required Python version
via PEP 723 inline metadata, and `uv run` downloads and manages a matching
interpreter on its own the first time it's needed.

**Do not `cd` into this skill's own directory.** `analyze.py`/`report.py`
write their output (`wikitrends-out/<run-id>/...`) relative to *your*
current working directory on purpose -- the skill directory may be
read-only, and outputs belong with the user's own work, not inside the
skill's install location. Instead, prefix every command below with this
skill's own base directory (the "Base directory for this skill" path shown
when this skill loads), keeping your shell wherever it already is:
```
uv run <base-directory>/scripts/resolve_topic.py --query ...
```
(A first attempt at just `scripts/resolve_topic.py` with no prefix will
fail with "No such file or directory" unless your shell happens to already
be inside the base directory -- use the full path from the start.)

1. **Resolve the topic**, unless you already have its Wikidata QID (e.g.
   from an earlier turn in this conversation):
   `uv run scripts/resolve_topic.py --query "<topic>" --query-lang <lang> --langs <lang1,lang2,...>`
   - It always returns every matching candidate, ranked by the search API,
     never a single guess.
   - **If more than one candidate has a substantially different
     description** (a real example: "Меркурій" in Wikidata matches the
     planet, a chemical element, a Roman god, a US city, and a warship),
     show the candidates to the user and ask which one they meant. Do not
     pick the top one silently.
   - A language with no article for that topic comes back as
     `{"status": "missing"}` in `articles` -- that's a normal, expected
     result, not an error.
   - **If the user's question doesn't name specific languages** (e.g.
     "compare interest across language editions" with no list given),
     **pick a reasonable, diverse default set yourself and proceed** --
     don't stop to ask which languages first. This is a normal scoping
     judgment call for you to make, unlike genuine topic ambiguity (the
     "Меркурій" case above, where the *topic itself* could mean several
     unrelated things) -- that one you always ask about; which languages
     to check, you don't.
2. **Analyze** using the QID(s) (or titles, for a repeat query -- see
   below):
   `uv run scripts/analyze.py --qids <QID[,QID...]> --langs <lang1,lang2,...> --last 24m`
3. **Answer the user** using only the numbers in the JSON output (rules
   below).
4. **Report**, if the user's own words ask for a "report"/"звіт"/"document"/
   "PDF"/"deck", or anything to hand off or share with someone else --
   generate the actual file, don't treat a well-formatted chat answer as a
   substitute:
   `uv run scripts/report.py --analysis-json <path from step 2> --lang <user's language> --summary "<your conclusion>"`
   Skip this step only when the user just asked a direct question in
   passing ("is interest growing?") with no indication they want something
   to share.

## Examples

**Compare a topic across language editions** ("Порівняй зростання
інтересу до інтервального голодування в польськомовній та чеськомовній
Wikipedia за останні два роки."):
```
uv run scripts/resolve_topic.py --query "інтервальне голодування" --query-lang uk --langs pl,cs
uv run scripts/analyze.py --qids Q1666254 --langs pl,cs,uk --last 24m
```

**Single topic, one language, with a trust check** ("Чи зростає інтерес
до астрономії в україномовній Wikipedia і наскільки цьому можна
довіряти?"):
```
uv run scripts/resolve_topic.py --query "астрономія" --query-lang uk --langs uk
uv run scripts/analyze.py --qids <QID> --langs uk --last 24m
```
Then read `series[0].trust` in the JSON and say the level *and* the
reasons out loud -- don't just report the growth number.

**Compare several topics within one language, then report** ("Порівняй
інтерес до вивчення англійської у вибраних мовних розділах і підготуй
короткий звіт"):
```
uv run scripts/analyze.py --titles "English language,Grammar,Duolingo" --lang en --last 24m
uv run scripts/report.py --analysis-json wikitrends-out/<run-id>/analysis.json --lang uk \
  --question "<the user's original question>" \
  --summary "<your conclusion, in the user's language>"
```

## How to write conclusions

- **Use only numbers that appear in the JSON.** Don't round further,
  don't estimate a missing value, don't interpolate.
- **Always state the trust level and at least one reason**, in every
  answer that cites a trend or growth number -- not just when it's low.
  Trust reasons come pre-written in `series[].trust.reasons` (English) and
  `series[].trust.reason_codes` (for `report.py` to localize); you can
  paraphrase them into your own answer.
- **Never claim interest = demand.** "Growing interest in X" is fine.
  "People want to buy X" is not something this data supports.
- **Prefer the normalized numbers** (`per_million` / `yoy_growth_normalized`)
  when comparing across languages -- raw view counts aren't comparable
  across language editions of very different sizes. Raw numbers
  (`yoy_growth_raw`) are fine for a single language over time.
- **If trust is "low"**, say so plainly and name what would improve it
  (usually: more months of data, or the topic just doesn't get enough
  traffic to say anything reliable) -- don't quietly present a low-trust
  number with the same confidence as a high-trust one.
- **A missing language (`"found": false`) is a real finding**, not a
  gap to paper over -- "there's no Polish Wikipedia article on this
  topic" is itself useful information about localization priority.

## Repeat / follow-up queries

Once you have a QID (from `resolve_topic.py`, or from earlier in this
conversation), a follow-up with a different date range, an added
language, or `--include-redirects` does **not** need `resolve_topic.py`
again -- call `analyze.py` directly with the same QID(s). Wikidata lookups
and pageview data are cached (7 days for Wikidata, per-month for
pageviews), so this is fast and makes no network calls for anything
already fetched. Only call `resolve_topic.py` again for a genuinely new
topic, or if the user wants to double check a candidate's description.

## Error codes

Every script prints `{"ok": false, "error_code", "message", "hint"}` on
failure. The `hint` is written to be a concrete next action -- follow it.
Quick reference:

| `error_code` | Meaning | What to do |
|---|---|---|
| `bad_arguments` | The CLI flags you passed are invalid or contradictory (e.g. both `--last` and `--start`, or neither) | Fix the flags per the message; `--help` on the script has examples |
| `qid_not_found` | The QID doesn't exist in Wikidata | Double-check it came from `resolve_topic.py`'s output, not typed from memory |
| `internal_request_error` | A title contains a character that broke the request URL | This is a bug in the skill, not your input -- report it, don't retry the same way |
| `upstream_unavailable` | Wikimedia returned repeated 429/5xx even after retries | Wait and try again later; not something to fix by changing your query |
| `network_error` | Couldn't reach one specific host (this skill talks to `www.wikidata.org`, `wikimedia.org`, and a `*.wikipedia.org` host per language -- a failure on one doesn't mean the others are blocked) | **Don't guess at the cause.** `hint` gives you a `curl` command for the exact URL that failed -- run it first. The real cause, and what to tell the user, differs by which Claude product you're running as (Claude Code's Bash sandbox vs. claude.ai/Claude Desktop's Capabilities network setting vs. an actual organizational block) -- see `references/interpreting.md`'s "`network_error`: verify before you diagnose" section for the full decision tree. Real incidents (three so far, independently): every prior run that skipped this and jumped straight to "org network policy" was wrong. |
| `http_error` | An unexpected HTTP status came back | Likely a malformed request; check the article title/date range you passed |
| `analysis_not_found` | `report.py --analysis-json` points at a file that doesn't exist | Run `analyze.py` first and pass its actual `analysis_json` path |
| `fonts_missing` | The skill's own font assets are missing | An installation problem with the skill itself, not your input |

## Language

**Answer the user, and write `--question`/`--summary` for `report.py`, in
the language the user is asking in.** `report.py --lang` natively
localizes its own template text (headers, trend/trust labels, trust
reasons) in Ukrainian and English; pass the closest of the two if the
user's language isn't one of those (the templates fall back to English,
but your own summary text should still be written in the user's actual
language). `SKILL.md` itself is in English by convention, but nothing
you say to the user should be.

## Details, on demand

- [references/methodology.md](references/methodology.md) -- how growth,
  trend significance, and the trust level are actually computed. Read
  this if the user asks *why* something got a particular trust level, or
  wants the statistical method explained.
- [references/api-notes.md](references/api-notes.md) -- Wikimedia/Wikidata
  API behavior and gotchas. Read this only if you're debugging an
  unexpected result or extending the skill's code -- not needed for normal use.
- [references/interpreting.md](references/interpreting.md) -- more worked
  examples of good vs. bad conclusion wording, and edge cases (seasonality,
  news spikes, very short series). Read this if a result looks surprising
  and you're not sure how to phrase it.
