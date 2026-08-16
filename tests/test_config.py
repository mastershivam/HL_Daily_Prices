from pathlib import Path

import config


def test_get_data_dir_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HL_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "somewhere-with-no-sibling")

    assert config.get_data_dir() is None


def test_get_data_dir_prefers_explicit_env_var(tmp_path, monkeypatch):
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv("HL_DATA_DIR", str(explicit_dir))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "somewhere-with-no-sibling")

    assert config.get_data_dir() == explicit_dir


def test_get_data_dir_finds_directory_nested_under_cwd(tmp_path, monkeypatch):
    # This is the GitHub Actions layout: `git clone` runs inside this
    # repo's checkout, nesting the data repo one level down from cwd.
    nested = tmp_path / config.DATA_DIR_NAME
    nested.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HL_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "somewhere-with-no-sibling")

    assert config.get_data_dir() == Path(config.DATA_DIR_NAME)


def test_get_data_dir_finds_sibling_of_repo_root(tmp_path, monkeypatch):
    # This is the real local dev layout: HL_Daily_Prices and
    # HL_Daily_Prices_Data sit as sibling folders (e.g. both directly under
    # ~/Random_Python/), neither nested inside the other - cwd-relative
    # resolution alone never finds this.
    repo_root = tmp_path / "HL_Daily_Prices"
    repo_root.mkdir()
    sibling = tmp_path / config.DATA_DIR_NAME
    sibling.mkdir()
    (tmp_path / "somewhere-else").mkdir()
    monkeypatch.chdir(tmp_path / "somewhere-else")
    monkeypatch.delenv("HL_DATA_DIR", raising=False)
    monkeypatch.setattr(config, "REPO_ROOT", repo_root)

    assert config.get_data_dir() == sibling


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
