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


# Matches a plausible numeric table cell: "60.110", "1,713.00", "100",
# "-58.24", and OCR's favourite garbled minus signs ("—750.00", "~600.00").
NUMBER_TOKEN_RE = re.compile(r"^[-−—~]?[£$]?[\d,]+(?:\.\d+)?%?$")


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


def _is_number_token(text: str) -> bool:
    return bool(NUMBER_TOKEN_RE.match(text))


def _clean_number_token(text: str) -> float | None:
    if not _is_number_token(text):
        return None
    cleaned = text.replace(",", "").replace("£", "").replace("$", "").replace("%", "")
    cleaned = re.sub(r"^[−—~]", "-", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_units_candidates(row_words: list[Word]) -> list[float]:
    """Every numeric-looking token in a row/window, left to right. HL's
    holdings table always lists Units as the leftmost figure (before
    Price/Value/Cost/Gain), so the caller takes candidates[0] as units
    rather than trying to guess from decimal-place count - some holdings
    show units to 2dp and others to 4dp, so that's not a reliable signal."""
    candidates = []
    for word in row_words:
        value = _clean_number_token(word.text)
        if value is not None:
            candidates.append(value)
    return candidates


_WORD_RE = re.compile(r"[a-z0-9]+")


def _word_tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def match_fund_name(
    row_text: str, known_funds: list[str], cutoff: float = 0.6, min_word_coverage: float = 0.8
) -> str | None:
    """Fuzzy-match text against known fund names from units.csv, tolerating
    OCR noise (misread characters, extra whitespace, a truncated column
    width, etc) - but NOT tolerating a wrong-but-similar-looking fund from
    the same family, e.g. "Baillie Gifford American" vs "Baillie Gifford
    Japanese" score 0.79 on raw character overlap despite being entirely
    different holdings, which is close enough to pass a naive cutoff and
    would silently attribute the wrong fund's units.

    So matching requires (a) most of the *words* in the known fund name to
    each have a close match somewhere in the candidate text - a swapped
    distinguishing word like American/Japanese fails this even though the
    strings look similar overall - and (b) the overall text still clears a
    basic character-level similarity floor, as a sanity check.
    """
    if not row_text.strip() or not known_funds:
        return None

    candidate_words = _word_tokens(row_text)
    if not candidate_words:
        return None

    best_fund = None
    best_coverage = 0.0
    for fund in known_funds:
        fund_words = _word_tokens(fund)
        if not fund_words:
            continue
        matched_words = sum(1 for fw in fund_words if difflib.get_close_matches(fw, candidate_words, n=1, cutoff=0.75))
        coverage = matched_words / len(fund_words)
        if coverage < min_word_coverage:
            continue
        char_ratio = difflib.SequenceMatcher(None, row_text.lower(), fund.lower()).ratio()
        if char_ratio < cutoff:
            continue
        if coverage > best_coverage:
            best_coverage = coverage
            best_fund = fund
    return best_fund


def describe_rows(words: list[Word]) -> list[str]:
    """Human-readable dump of the OCR'd table rows, for debugging when
    matching fails - shows exactly what OCR/row-grouping produced."""
    return [" ".join(w.text for w in row) for row in group_words_into_rows(words)]


def parse_holdings_from_words(
    words: list[Word], known_funds: list[str], cutoff: float = 0.6, merge_window: int = 3
) -> tuple[dict[str, float], list[dict[str, object]]]:
    """Walk the screenshot's rows and, for each holding, pull out its name
    text (with any numeric cells filtered out) and its units figure (the
    first number on the smallest merge of rows that has both). HL wraps
    long fund names onto their own line above a separate row of figures,
    and sometimes a trailing "Class X - Accumulation (GBP)" line below
    that - merge_window lets a holding span up to that many consecutive
    rows before giving up.

    Returns (holdings, unmatched):
    - holdings: {fund_name: units} for rows confidently matched against a
      fund already in units.csv.
    - unmatched: [{"text": ..., "units": ...}] for rows that had a
      plausible units figure but didn't match any known fund - almost
      always a real holding that just isn't in units.csv yet, surfaced so
      it can be added by hand (OCR has no way to know the HL URL/ticker a
      brand new fund needs).
    """
    rows = group_words_into_rows(words)
    holdings: dict[str, float] = {}
    unmatched: list[dict[str, object]] = []
    consumed: set[int] = set()

    for start in range(len(rows)):
        if start in consumed:
            continue

        best = None
        for span in range(1, merge_window + 1):
            if start + span > len(rows):
                break
            window_indices = list(range(start, start + span))
            window_words = [w for i in window_indices for w in rows[i]]
            name_words = [w for w in window_words if not _is_number_token(w.text)]
            candidates = extract_units_candidates(window_words)
            if name_words and candidates:
                best = (name_words, candidates[0], window_indices)
                break
        if best is None:
            continue

        name_words, units, window_indices = best
        consumed.update(window_indices)

        # Also pull in a trailing continuation line with no units number of
        # its own (e.g. "Class B - Accumulation (GBP)") for name matching -
        # the fund's full official name usually includes that suffix, so
        # leaving it out under-counts word coverage and can cause a real
        # match to be missed.
        end = max(window_indices) + 1
        if end < len(rows) and end not in consumed and not extract_units_candidates(rows[end]):
            name_words = name_words + rows[end]
            consumed.add(end)

        name_text = " ".join(w.text for w in name_words)
        fund = match_fund_name(name_text, known_funds, cutoff=cutoff)
        if fund and fund not in holdings:
            holdings[fund] = units
        else:
            unmatched.append({"text": name_text, "units": units})

    return holdings, unmatched


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
