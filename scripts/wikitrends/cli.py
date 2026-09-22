import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Tuple

from .cache import Cache
from .errors import AppError
from .http import build_session


def run_cli(main_fn: Callable[[], Any]) -> None:
    """Print main_fn()'s return value as one line of compact JSON. On
    AppError, print its .to_json() instead and exit with status 1 — this is
    the one place all three scripts implement the stdout/error contract, so
    it only needs to be right once."""
    try:
        result = main_fn()
    except AppError as exc:
        print(json.dumps(exc.to_json(), ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


def make_session_and_cache() -> Tuple[Any, Cache]:
    contact = os.environ.get("WIKITRENDS_CONTACT")
    return build_session(contact=contact), Cache()


def new_run_dir(base: Path = Path("wikitrends-out")) -> Path:
    """A fresh ./wikitrends-out/<run-id>/ directory (per the spec: outputs
    go in the caller's cwd, never inside the skill directory) for one
    analyze.py run's analysis.json + chart.png. report.py doesn't call this
    -- it writes its PDF as a sibling of the analysis.json path it's given."""
    run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
