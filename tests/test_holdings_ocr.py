from holdings_ocr import (
    Word,
    describe_rows,
    extract_units_candidates,
    group_words_into_rows,
    match_fund_name,
    parse_holdings_from_words,
)


def _row_words(y: int, texts_with_x: list[tuple[str, int]]) -> list[Word]:
    return [Word(text=text, left=x, top=y, width=40, height=12) for text, x in texts_with_x]


def test_group_words_into_rows_groups_by_similar_vertical_position():
    words = (
        _row_words(100, [("Baillie", 0), ("Gifford", 60)])
        + _row_words(150, [("Vanguard", 0), ("FTSE", 60)])
        + _row_words(103, [("Japanese", 120)])  # same row as y=100, within tolerance
    )

    rows = group_words_into_rows(words, y_tolerance=10)

    assert len(rows) == 2
    assert [w.text for w in rows[0]] == ["Baillie", "Gifford", "Japanese"]
    assert [w.text for w in rows[1]] == ["Vanguard", "FTSE"]


def test_extract_units_candidates_returns_all_numeric_tokens_in_order():
    # Real HL rows don't consistently use 3+ decimal places for units (some
    # holdings show just 2dp), so extraction can't rely on decimal count -
    # it returns every numeric cell left-to-right and the caller takes the
    # first (leftmost = Units column in HL's table).
    row = _row_words(0, [("60.110", 0), ("1,713.00", 80), ("1,029.68", 160), ("900.00", 240)])
    assert extract_units_candidates(row) == [60.110, 1713.00, 1029.68, 900.00]


def test_extract_units_candidates_handles_ocr_garbled_minus_signs():
    row = _row_words(0, [("307.37", 0), ("—750.00", 80)])
    assert extract_units_candidates(row) == [307.37, -750.00]


def test_extract_units_candidates_ignores_non_numeric_words():
    row = _row_words(0, [("Baillie", 0), ("Gifford", 40), ("*", 80)])
    assert extract_units_candidates(row) == []


def test_match_fund_name_tolerates_ocr_noise():
    known = ["Baillie Gifford Japanese", "Vanguard FTSE Global All Cap"]
    assert match_fund_name("Baillie Giffbrd Japanese B Acc", known) == "Baillie Gifford Japanese"


def test_match_fund_name_returns_none_below_cutoff():
    known = ["Baillie Gifford Japanese"]
    assert match_fund_name("Completely unrelated text", known, cutoff=0.6) is None


def test_parse_holdings_from_words_returns_units_per_matched_fund():
    known_funds = ["Baillie Gifford Japanese", "Vanguard FTSE Global All Cap"]
    words = (
        _row_words(100, [("Baillie", 0), ("Gifford", 60), ("Japanese", 120), ("105.1234", 300)])
        + _row_words(150, [("Vanguard", 0), ("FTSE", 60), ("Global", 120), ("All", 180), ("Cap", 220), ("50.0000", 300)])
    )

    holdings, unmatched = parse_holdings_from_words(words, known_funds)

    assert holdings == {
        "Baillie Gifford Japanese": 105.1234,
        "Vanguard FTSE Global All Cap": 50.0,
    }
    assert unmatched == []


def test_parse_holdings_from_words_skips_rows_without_a_units_number():
    known_funds = ["Baillie Gifford Japanese"]
    words = _row_words(100, [("Baillie", 0), ("Gifford", 60), ("Japanese", 120)])

    holdings, unmatched = parse_holdings_from_words(words, known_funds)
    assert holdings == {}
    assert unmatched == []


def test_parse_holdings_from_words_handles_fund_name_wrapped_across_two_lines():
    # HL's holdings table wraps long fund names onto a second line - the
    # name and its units figure can end up as two separate OCR "rows".
    known_funds = ["Vanguard FTSE Global All Cap Index Fund Accumulation"]
    words = (
        _row_words(100, [("Vanguard", 0), ("FTSE", 80), ("Global", 140), ("All", 200)])
        + _row_words(122, [("Cap", 0), ("Index", 40), ("Fund", 100), ("Accumulation", 150), ("87.6543", 320)])
    )

    holdings, unmatched = parse_holdings_from_words(words, known_funds)

    assert holdings == {"Vanguard FTSE Global All Cap Index Fund Accumulation": 87.6543}


def test_parse_holdings_from_words_reports_unmatched_holdings_instead_of_dropping_them():
    # Nothing in units.csv matches what's actually in the screenshot -
    # these should come back as unmatched candidates (with readable text +
    # units), not silently vanish.
    known_funds = ["Baillie Gifford Japanese"]
    words = _row_words(100, [("Jupiter", 0), ("India", 70)]) + _row_words(
        122, [("255.61", 0), ("248.24", 80), ("634.53", 160), ("600.00", 240), ("34.53", 320), ("5.76", 380)]
    )

    holdings, unmatched = parse_holdings_from_words(words, known_funds)

    assert holdings == {}
    assert len(unmatched) == 1
    assert unmatched[0]["text"] == "Jupiter India"
    assert unmatched[0]["units"] == 255.61


def test_parse_holdings_from_words_matches_real_hl_table_layout_with_trailing_class_line():
    # Regression test based on an actual HL holdings screenshot: name row,
    # then a separate numbers row (units shown to only 2dp here - not 3-6),
    # then a trailing "Class B - Accumulation (GBP)" line that shouldn't
    # bleed into the next holding.
    known_funds = ["Baillie Gifford American Class B Accumulation"]
    words = (
        _row_words(100, [("Baillie", 0), ("Gifford", 70), ("American", 140)])
        + _row_words(122, [("60.110", 0), ("1,713.00", 90), ("1,029.68", 190), ("900.00", 290), ("129.68", 370), ("14.41", 440)])
        + _row_words(144, [("Class", 0), ("B", 50), ("-", 70), ("Accumulation", 90), ("(GBP)", 180)])
        + _row_words(166, [("BlackRock", 0), ("Continental", 90)])
    )

    holdings, unmatched = parse_holdings_from_words(words, known_funds)

    assert holdings == {"Baillie Gifford American Class B Accumulation": 60.110}
    # The trailing class-label row should have been consumed alongside the
    # match, not merged into the next (unrelated, and here incomplete)
    # holding's name.
    assert not any("BlackRock" in u["text"] and "Class" in u["text"] for u in unmatched)


def test_describe_rows_returns_joined_text_per_row():
    words = _row_words(100, [("Baillie", 0), ("Gifford", 60)]) + _row_words(150, [("Vanguard", 0)])
    assert describe_rows(words) == ["Baillie Gifford", "Vanguard"]
