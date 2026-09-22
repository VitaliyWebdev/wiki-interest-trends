import json
import os
import sys
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
