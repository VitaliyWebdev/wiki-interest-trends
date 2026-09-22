# errors.py + cli.py — the stdout/error contract

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/errors.py`, `skills/wiki-interest-trends/scripts/wikitrends/cli.py`
**Tests:** `skills/wiki-interest-trends/tests/test_errors.py`, `skills/wiki-interest-trends/tests/test_cli.py`

## What it's for

The spec requires every script to speak the same tiny protocol to the agent:
success is one line of compact JSON on stdout, failure is
`{"ok": false, "error_code", "message", "hint"}` also on stdout (not
stderr — a weak model reads stdout, not exception tracebacks). These two
files are where that protocol is implemented exactly once, so
`resolve_topic.py`, `analyze.py`, and `report.py` can't drift from each
other.

## `errors.py`

```python
@dataclass
class AppError(Exception):
    error_code: str
    message: str
    hint: str

    def to_json(self) -> dict  # {"ok": False, "error_code", "message", "hint"}
```

Every module that can fail in a way the *agent* needs to react to (not a
bug we need to fix) raises `AppError` with a specific `error_code` and a
`hint` that is a concrete next action, e.g. "Try a shorter date range" —
not "an error occurred". `error_code` values in use so far:
`qid_not_found` (wikidata.py), `upstream_unavailable`, `network_error`,
`http_error` (http.py). Each new failure mode a script can hit gets its own
`error_code` — see `skills/wiki-interest-trends/SKILL.md`'s error code table
for the agent-facing list; grep `error_code=` across
`skills/wiki-interest-trends/scripts/` for the authoritative one in code.

## `cli.py`

```python
run_cli(main_fn: Callable[[], Any]) -> None
make_session_and_cache() -> (requests.Session, Cache)
```

`run_cli` calls `main_fn()`. On success, `json.dumps(result)` to stdout. On
`AppError`, `json.dumps(exc.to_json())` to stdout and `sys.exit(1)`. Any
*other* exception is intentionally **not** caught here — an unexpected
`KeyError`/`TypeError` is a bug, and a raw traceback on stderr is more
useful for debugging than swallowing it into a fake `AppError`.

`make_session_and_cache()` wires up a `requests.Session` (with UA from
`WIKITRENDS_CONTACT`) and a `Cache` (path from `WIKITRENDS_CACHE`, or the
default) in one call — every script's `main()` starts with this line.

Every CLI script keeps its core logic as a plain function that takes
`(session, cache, ...)` and returns a dict (see `resolve_topic()` in
`resolve_topic.py`) separate from its `main()`/argparse glue. Tests call
the plain function directly with a fake session; `main()` itself is thin
enough not to need its own tests beyond `--help` rendering correctly.
