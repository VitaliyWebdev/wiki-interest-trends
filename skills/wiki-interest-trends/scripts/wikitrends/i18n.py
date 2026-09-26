from typing import Mapping, Optional, TypeVar

T = TypeVar("T")

SUPPORTED_LANGS = ("en", "uk", "pl", "cs")
DEFAULT_LANG = "en"

# CLDR abbreviated month names. Not strftime("%b"): that follows the
# process locale, which is "C" (English) wherever these scripts run.
MONTHS_SHORT = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "uk": ["січ.", "лют.", "бер.", "квіт.", "трав.", "черв.", "лип.", "серп.", "вер.", "жовт.", "лист.", "груд."],
    "pl": ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"],
    "cs": ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"],
}
THOUSANDS_SEP = {"en": ",", "uk": "\u00a0", "pl": "\u00a0", "cs": "\u00a0"}
DECIMAL_SEP = {"en": ".", "uk": ",", "pl": ",", "cs": ","}
THOUSAND_SUFFIX = {"en": "K", "uk": "\u00a0тис.", "pl": "\u00a0tys.", "cs": "\u00a0tis."}
MILLION_SUFFIX = {"en": "M", "uk": "\u00a0млн", "pl": "\u00a0mln", "cs": "\u00a0mil."}
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
    """27880 -> "27.9K" / "27,9 тис." (no-break space), 328950 -> "329K",
    1260000 -> "1.3M" -- for KPI cards, where the exact number is in the
    table right below. One decimal only while it adds a meaningful digit:
    never "329.0K" or "14.0K"."""
    if abs(value) < 1000:
        return format_int(value, lang)
    # From 999,500 up the thousands form would print "1000K".
    size, suffix = (1_000_000, MILLION_SUFFIX) if abs(value) >= 999_500 else (1000, THOUSAND_SUFFIX)
    scaled = value / size
    text = f"{scaled:.0f}" if abs(scaled) >= 99.95 else f"{scaled:.1f}".removesuffix(".0")
    return text.replace(".", pick(DECIMAL_SEP, lang)) + pick(suffix, lang)


def format_pct(value: Optional[float]) -> str:
    """0.42 -> "+42%", -0.2 -> "-20%" but with a real minus sign (U+2212),
    None -> an em dash. Same in every supported language."""
    if value is None:
        return "\u2014"
    return f"{value:+.0%}".replace("-", MINUS)
