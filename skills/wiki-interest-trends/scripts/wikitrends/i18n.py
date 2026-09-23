from typing import Mapping, TypeVar

T = TypeVar("T")

SUPPORTED_LANGS = ("en", "uk")
DEFAULT_LANG = "en"


def pick(table: Mapping[str, T], lang: str) -> T:
    """The one fallback rule for every localized string table: an
    unsupported language gets English, never a KeyError -- a less
    localized output beats a failed one."""
    return table.get(lang, table[DEFAULT_LANG])
