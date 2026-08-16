from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

DATA_DIR_NAME = "HL_Daily_Prices_Data"
REPO_ROOT = Path(__file__).resolve().parent


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def env_flag(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return env(name, fallback).lower() in {"true", "1", "yes"}


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipients: tuple[str, ...]
    email_enabled: bool = True

    @property
    def enabled(self) -> bool:
        # EMAIL_ENABLED is an explicit kill switch, separate from whether
        # SMTP credentials happen to be present - so email can be turned
        # off without deleting/losing the SMTP config for later.
        if not self.email_enabled:
            return False
        return any([self.host, self.user, self.password, self.sender, self.recipients])


@dataclass(frozen=True)
class PushSettings:
    base_url: str
    topic: str
    token: str

    @property
    def enabled(self) -> bool:
        return bool(self.topic)


def get_email_settings() -> EmailSettings:
    host = env("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    user = env("SMTP_USER") or env("EMAIL_ADDRESS")
    password = env("SMTP_PASS") or env("EMAIL_APP_PASSWORD")
    sender = env("EMAIL_FROM") or user or env("EMAIL_ADDRESS")
    recipients_value = env("EMAIL_TO") or env("EMAIL_RECIPIENTS")
    recipients = tuple(r.strip() for r in recipients_value.split(",") if r.strip()) if recipients_value else ()
    return EmailSettings(
        host=host,
        port=port,
        user=user,
        password=password,
        sender=sender,
        recipients=recipients,
        email_enabled=env_flag("EMAIL_ENABLED", default=True),
    )


def get_push_settings() -> PushSettings:
    return PushSettings(
        base_url=env("NTFY_BASE_URL") or "https://ntfy.sh",
        topic=env("NTFY_TOPIC"),
        token=env("NTFY_TOKEN"),
    )


def get_debug_mode() -> bool:
    return env_flag("DEBUG", default=False)


def get_data_dir() -> Path | None:
    """Locate the private HL_Daily_Prices_Data directory holding
    units.csv/transactions.csv/daily_totals.csv, checked in order:

    1. HL_DATA_DIR env var - an explicit override (absolute or relative).
    2. ./HL_Daily_Prices_Data relative to the current working directory -
       what GitHub Actions produces (`git clone` runs *inside* this repo's
       checkout, nesting the data repo one level down).
    3. A directory named HL_Daily_Prices_Data that's a *sibling* of this
       repo's own directory - how the two repos actually sit on disk for
       local development (two separate folders side by side, e.g. both
       directly under ~/Random_Python/, neither nested in the other).
       Resolving purely off cwd (option 2) never finds it in that layout
       even though it's right there, so this used to silently fall back to
       a stale/placeholder local units.csv instead of the real data.

    Returns None if none of these exist, so callers fall back to purely
    local files (daily_totals.csv, units.csv, transactions.csv in this
    repo's own root).
    """
    env_dir = env("HL_DATA_DIR")
    if env_dir:
        candidate = Path(env_dir).expanduser()
        if candidate.exists():
            return candidate

    cwd_relative = Path(DATA_DIR_NAME)
    if cwd_relative.exists():
        return cwd_relative

    sibling = REPO_ROOT.parent / DATA_DIR_NAME
    if sibling.exists():
        return sibling

    return None


def get_watchlist_tickers() -> tuple[str, ...]:
    """Yahoo Finance symbols to show as reference quotes alongside the
    portfolio total (not counted in the total itself). Previously this was
    a single ticker ("ELIX.L") hardcoded in main.py; it's now a
    comma-separated WATCHLIST_TICKERS env var, defaulting to the same
    ticker so existing behaviour is unchanged if it's left unset.
    """
    raw = env("WATCHLIST_TICKERS")
    if not raw:
        return ("ELIX.L",)
    return tuple(t.strip() for t in raw.split(",") if t.strip())
