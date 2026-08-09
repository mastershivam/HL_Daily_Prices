"""Read current holdings (fund name + units) off a screenshot of your HL
holdings page using local OCR, so `invest.py --sync-from-image` can
reconcile units.csv without Claude (or anyone) reading the image, and
without ever logging into HL or storing account credentials anywhere.

The OCR call itself (run_ocr) is a thin wrapper kept separate from the
parsing logic below, so the parsing/matching can be unit-tested with
synthetic word boxes even where the tesseract binary isn't installed.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int


# HL lists units to several decimal places (e.g. "123.4567"), which is what
# distinguishes a units figure from a 2dp price/value figure on the same row.
UNITS_NUMBER_RE = re.compile(r"^-?[\d,]+\.\d{3,6}$")


def group_words_into_rows(words: list[Word], y_tolerance: int = 10) -> list[list[Word]]:
    """Group OCR word boxes into visual table rows by vertical position.
    OCR returns individual words with bounding boxes, not rows - this
    reconstructs the table layout so a fund name and its units figure
    (which are on the same visual row but separate "words") can be matched
    back up."""
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.left)):
        placed = False
        for row in rows:
            if abs(row[0].top - word.top) <= y_tolerance:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda w: w.left)
    rows.sort(key=lambda row: row[0].top)
    return rows


def extract_units_candidates(row: list[Word]) -> list[float]:
    """Numbers on a row that look like a plausible units figure."""
    candidates = []
    for word in row:
        cleaned = word.text.replace(",", "")
        if UNITS_NUMBER_RE.match(cleaned):
            try:
                candidates.append(float(cleaned))
            except ValueError:
                continue
    return candidates


def match_fund_name(row_text: str, known_funds: list[str], cutoff: float = 0.6) -> str | None:
    """Fuzzy-match a row's OCR'd text against known fund names from
    units.csv, tolerating OCR noise (misread characters, extra whitespace,
    a truncated column width, etc)."""
    if not row_text.strip() or not known_funds:
        return None
    matches = difflib.get_close_matches(row_text.lower(), [f.lower() for f in known_funds], n=1, cutoff=cutoff)
    if not matches:
        return None
    matched_lower = matches[0]
    for fund in known_funds:
        if fund.lower() == matched_lower:
            return fund
    return None


def parse_holdings_from_words(words: list[Word], known_funds: list[str], cutoff: float = 0.6) -> dict[str, float]:
    """Return {fund_name: units} for every known fund confidently matched to
    a row in the screenshot. Funds not found in the screenshot are simply
    left out - a missed OCR match should never be silently treated as
    "sold to zero"."""
    rows = group_words_into_rows(words)
    holdings: dict[str, float] = {}
    for row in rows:
        row_text = " ".join(w.text for w in row)
        fund = match_fund_name(row_text, known_funds, cutoff=cutoff)
        if not fund or fund in holdings:
            continue
        candidates = extract_units_candidates(row)
        if not candidates:
            continue
        holdings[fund] = candidates[0]
    return holdings


def run_ocr(image_path: str):
    """Run local OCR (pytesseract + the system tesseract binary) over a
    screenshot and return its word boxes. Requires `pip install pytesseract
    pillow` and the tesseract binary itself (e.g. `brew install tesseract`
    on macOS) - imported lazily so the rest of this module, and its tests,
    work without either installed."""
    import pytesseract
    from PIL import Image

    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        words.append(
            Word(
                text=text,
                left=data["left"][i],
                top=data["top"][i],
                width=data["width"][i],
                height=data["height"][i],
            )
        )
    return words
