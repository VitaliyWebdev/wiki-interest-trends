from typing import Mapping, Optional, TypeVar

T = TypeVar("T")

SUPPORTED_LANGS = ("en", "uk")
DEFAULT_LANG = "en"

# CLDR abbreviated month names. Not strftime("%b"): that follows the
# process locale, which is "C" (English) wherever these scripts run.
MONTHS_SHORT = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "uk": ["січ.", "лют.", "бер.", "квіт.", "трав.", "черв.", "лип.", "серп.", "вер.", "жовт.", "лист.", "груд."],
}
THOUSANDS_SEP = {"en": ",", "uk": "\u00a0"}
DECIMAL_SEP = {"en": ".", "uk": ","}
THOUSAND_SUFFIX = {"en": "K", "uk": "\u00a0тис."}
MINUS = "\u2212"  # a real minus sign, not a hyphen


def pick(table: Mapping[str, T], lang: str) -> T:
    """The one fallback rule for every localized string table: an
    unsupported language gets English, never a KeyError -- a less
    localized output beats a failed one."""
    return table.get(lang, table[DEFAULT_LANG])


def month_label(month: int, year: Optional[int], lang: str) -> str:
    name = pick(MONTHS_SHORT, lang)[month - 1]
    return f"{name} {year}" if year is not None else name


def format_int(value: float, lang: str) -> str:
    return f"{value:,.0f}".replace(",", pick(THOUSANDS_SEP, lang))


def format_compact(value: float, lang: str) -> str:
    """27880 -> "27.9K" / "27,9 тис." (no-break space) -- for KPI cards, where
    the exact number is in the table right below."""
    if abs(value) < 1000:
        return format_int(value, lang)
    return f"{value / 1000:.1f}".replace(".", pick(DECIMAL_SEP, lang)) + pick(THOUSAND_SUFFIX, lang)


def format_pct(value: Optional[float]) -> str:
    """0.42 -> "+42%", -0.2 -> "-20%" but with a real minus sign (U+2212),
    None -> an em dash. Same in every supported language."""
    if value is None:
        return "\u2014"
    return f"{value:+.0%}".replace("-", MINUS)
