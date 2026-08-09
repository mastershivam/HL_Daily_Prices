import config


def test_get_email_settings_disabled_via_email_enabled_flag(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("EMAIL_TO", "me@example.com")

    settings = config.get_email_settings()

    assert settings.enabled is False


def test_get_email_settings_enabled_when_flag_true_and_credentials_present(monkeypatch):
    monkeypatch.delenv("EMAIL_ENABLED", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("EMAIL_TO", "me@example.com")

    settings = config.get_email_settings()

    assert settings.enabled is True


def test_get_email_settings_disabled_when_no_credentials_even_if_flag_true(monkeypatch):
    for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "EMAIL_TO", "EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENTS"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("EMAIL_ENABLED", raising=False)

    settings = config.get_email_settings()

    assert settings.enabled is False
