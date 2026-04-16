from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


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

    @property
    def enabled(self) -> bool:
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
    )


def get_push_settings() -> PushSettings:
    return PushSettings(
        base_url=env("NTFY_BASE_URL") or "https://ntfy.sh",
        topic=env("NTFY_TOPIC"),
        token=env("NTFY_TOKEN"),
    )


def get_debug_mode() -> bool:
    return env_flag("DEBUG", default=False)
