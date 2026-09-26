from pathlib import Path
from typing import Tuple

from .errors import AppError

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REGULAR_FILE = "DejaVuSans.ttf"
BOLD_FILE = "DejaVuSans-Bold.ttf"
# Tried in order for any character DejaVu Sans lacks. DejaVu has no CJK at
# all, so zh/ja/ko article titles used to print as empty boxes. NanumGothic
# covers Korean (no ideographs or kana); Droid Sans Fallback covers Chinese
# and Japanese but has no Latin (not even a space) and no Hangul syllables.
# Nanum must come first: Droid does have Hangul jamo, and with it ahead
# matplotlib drew 간 as 가 + a separate ㄴ. Regular weight only: a bold CJK
# label is drawn regular rather than faked.
FALLBACK_FILES: Tuple[str, ...] = ("NanumGothic-Regular.ttf", "DroidSansFallbackFull.ttf")
ALL_FILES: Tuple[str, ...] = (REGULAR_FILE, BOLD_FILE) + FALLBACK_FILES


def require_fonts(fonts_dir: Path = FONTS_DIR) -> None:
    missing = [name for name in ALL_FILES if not (fonts_dir / name).exists()]
    if missing:
        raise AppError(
            error_code="fonts_missing",
            message=f"Fonts not found under {fonts_dir}: {', '.join(missing)}",
            hint="Reinstall the skill: every file in assets/fonts/ ships with it.",
        )
