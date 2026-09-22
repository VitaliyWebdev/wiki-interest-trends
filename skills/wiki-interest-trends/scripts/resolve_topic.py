#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests==2.34.2"]
# ///
"""Resolve a topic (in any language) to Wikidata candidates and, for each
candidate, the article title in every requested Wikipedia language edition.

Always returns every matching candidate (up to --limit) — it never guesses
which one you meant. If a query matches several substantially different
topics (e.g. "Меркурій" matches the planet, the element, and the Roman god),
look at each candidate's description and ask the user which one they meant
before calling analyze.py.

Examples:
  uv run scripts/resolve_topic.py --query "інтервальне голодування" --query-lang uk --langs pl,cs
  uv run scripts/resolve_topic.py --query "astronomy" --query-lang en --langs uk --limit 3
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from wikitrends.cache import Cache
from wikitrends.cli import make_session_and_cache, run_cli
from wikitrends.wikidata import get_sitelinks, search_entities


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolve_topic.py",
        description=(
            "Find a topic's Wikidata QID and its Wikipedia article title in "
            "each requested language."
        ),
        epilog=(
            "Examples:\n"
            '  uv run scripts/resolve_topic.py --query "інтервальне голодування"'
            " --query-lang uk --langs pl,cs\n"
            '  uv run scripts/resolve_topic.py --query "astronomy" --query-lang en'
            " --langs uk --limit 3\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", required=True, help="Topic to search for, written in --query-lang")
    parser.add_argument("--query-lang", required=True, help="Language code of --query, e.g. uk")
    parser.add_argument(
        "--langs",
        required=True,
        help="Comma-separated Wikipedia language codes to look up articles in, e.g. pl,cs",
    )
    parser.add_argument("--limit", type=int, default=5, help="Max candidates to return (default: 5)")
    return parser


def resolve_topic(
    session: Any, cache: Cache, query: str, query_lang: str, langs: List[str], limit: int = 5
) -> Dict[str, Any]:
    candidates = search_entities(session, cache, query=query, language=query_lang, limit=limit)

    result = []
    for candidate in candidates:
        articles = get_sitelinks(session, cache, qid=candidate.qid, langs=langs)
        result.append(
            {
                "qid": candidate.qid,
                "label": candidate.label,
                "description": candidate.description,
                "articles": {
                    lang: (
                        {"status": "found", "title": lookup.title}
                        if lookup.status == "found"
                        else {"status": "missing"}
                    )
                    for lang, lookup in articles.items()
                },
            }
        )
    return {"ok": True, "candidates": result}


def main(argv=None) -> None:
    args = build_arg_parser().parse_args(argv)
    langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()]
    session, cache = make_session_and_cache()
    run_cli(
        lambda: resolve_topic(session, cache, args.query, args.query_lang, langs, args.limit)
    )


if __name__ == "__main__":
    main()
