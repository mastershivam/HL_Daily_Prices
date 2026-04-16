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
