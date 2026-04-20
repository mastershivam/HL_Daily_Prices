from notifications import build_notification_subject, format_push_message


def test_build_notification_subject():
    assert build_notification_subject("2026-04-16") == "Daily Portfolio Summary - 2026-04-16"


def test_format_push_message_with_previous_total():
    message = format_push_message(12345.67, 12193.57)
    assert message == "Portfolio total: GBP 12,345.67 (+152.10, +1.25%)"


def test_format_push_message_without_previous_total():
    assert format_push_message(12345.67, None) == "Portfolio total: GBP 12,345.67"


def test_format_push_message_with_zero_previous_total():
    assert format_push_message(12345.67, 0.0) == "Portfolio total: GBP 12,345.67 (+12,345.67)"


def test_format_push_message_with_elix_quote_and_change():
    message = format_push_message(
        12345.67,
        12193.57,
        elix_price_pence=152.5,
        elix_change_pence=1.5,
        elix_change_pct=1.23,
    )
    assert message == "Portfolio total: GBP 12,345.67 (+152.10, +1.25%)\nLON:ELIX: 152.50p (+1.50p DoD, +1.23%)"


def test_format_push_message_with_elix_quote_without_change():
    message = format_push_message(12345.67, None, elix_price_pence=152.5)
    assert message == "Portfolio total: GBP 12,345.67\nLON:ELIX: 152.50p"


def test_format_push_message_with_elix_quote_and_only_pct_change():
    message = format_push_message(12345.67, None, elix_price_pence=152.5, elix_change_pct=-0.45)
    assert message == "Portfolio total: GBP 12,345.67\nLON:ELIX: 152.50p (-0.45% DoD)"
