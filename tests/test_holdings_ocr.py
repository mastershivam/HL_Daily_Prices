from holdings_ocr import (
    Word,
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


def test_extract_units_candidates_picks_out_decimal_looking_numbers():
    row = _row_words(0, [("Baillie", 0), ("Gifford", 40), ("123.4567", 80), ("£45.00", 130)])
    assert extract_units_candidates(row) == [123.4567]


def test_extract_units_candidates_ignores_2dp_currency_values():
    row = _row_words(0, [("Fund", 0), ("45.00", 40)])
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

    holdings = parse_holdings_from_words(words, known_funds)

    assert holdings == {
        "Baillie Gifford Japanese": 105.1234,
        "Vanguard FTSE Global All Cap": 50.0,
    }


def test_parse_holdings_from_words_skips_rows_without_a_units_number():
    known_funds = ["Baillie Gifford Japanese"]
    words = _row_words(100, [("Baillie", 0), ("Gifford", 60), ("Japanese", 120)])

    assert parse_holdings_from_words(words, known_funds) == {}
