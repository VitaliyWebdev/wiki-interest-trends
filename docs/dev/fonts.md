# fonts.py — bundled fonts and CJK fallback

**Files:** `skills/wiki-interest-trends/scripts/wikitrends/fonts.py`,
`report.py` (`_runs`, `_width`, `_split_mixed`, `_RunText`),
`chart.py` (`_font_family`)
**Tests:** `test_chart.py` / `test_report.py`, the `cjk`, `chinese` and
`hangul` tests

## What ships

| File | Covers | License | Source |
|---|---|---|---|
| `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf` | Latin, Cyrillic, Greek, ... | Bitstream Vera (`LICENSE.txt`) | matplotlib's bundle |
| `NanumGothic-Regular.ttf` (2.0 MB) | Hangul | OFL (`LICENSE-NanumGothic.txt`) | github.com/google/fonts `ofl/nanumgothic/` |
| `DroidSansFallbackFull.ttf` (4.0 MB) | CJK ideographs, kana | Apache 2.0 (`LICENSE-DroidSansFallback.txt`) | AOSP `platform_frameworks_base` tag `android-7.1.2_r36`, `data/fonts/` |

sha256: NanumGothic `76f45ef4…2d31`, DroidSansFallbackFull `acb6440a…77b8`.

Why these two and not Noto Sans CJK: reportlab only reads TrueType
(`glyf`) outlines, and Noto Sans CJK is CFF. Google Fonts' TrueType
Noto Sans SC is a 17.8 MB variable font with no Hangul. Droid + Nanum are
6 MB together, both `glyf`, and cover all three languages.

## The fallback order: Nanum, then Droid

`FALLBACK_FILES` is tried in order for any character DejaVu lacks. Nanum
has no ideographs or kana, so it never takes Chinese or Japanese. Droid
has no Hangul *syllables* but does have Hangul *jamo*. With Droid first,
matplotlib decomposed 간 into 가 + ᆫ and drew the jamo from Droid, so a
live chart showed "가ㄴ헐적". The PDF's extracted text still read "간",
so the test checks which font drew each character, not the text.

## matplotlib vs reportlab

- **matplotlib** does per-glyph fallback itself once `font.family` is a
  list. The CJK fonts are regular-only, so bold labels log
  "Failed to find font weight bold". That logger is set to ERROR so the
  expected noise doesn't reach the agent's stderr.
- **reportlab** draws a string in one font. `_runs()` splits text into
  (font, text) pieces, and everything that draws, measures (`_width`) or
  cuts (`_fit`) goes through it. Whitespace always stays in the base
  font, because Droid has no space glyph. A string DejaVu covers fully is
  one run, so Latin and Cyrillic text takes exactly the old path.
- **Wrapping:** `simpleSplit` only breaks at spaces, and CJK has none.
  `_split_mixed` is used only when a paragraph needs a fallback font, and
  breaks between any two CJK characters or at spaces.
- **Table cells** take one `FONTNAME`, so a title that needs a fallback
  becomes a `_RunText` flowable instead of a plain string.

## Not covered

Scripts that need shaping (Devanagari, Thai, Arabic joining): neither
library does complex text layout, so bundling a font wouldn't make them
correct, only visible as unjoined letters.
