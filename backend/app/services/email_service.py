"""Email provider abstraction (Step 54A)."""

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import TYPE_CHECKING

from app.core.secret_masking import mask_secrets_in_text

if TYPE_CHECKING:
    from app.core.config import Settings

_log = logging.getLogger("cns.email")


class EmailProvider(ABC):
    @abstractmethod
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> bool:
        """Return True on success."""


class DisabledEmailProvider(EmailProvider):
    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
        _log.debug("email disabled; skip to=%s subject=%s", to_email, subject)
        return False


class ConsoleEmailProvider(EmailProvider):
    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
        _log.info(
            "console email to=%s subject=%s body=%s",
            to_email,
            mask_secrets_in_text(subject),
            mask_secrets_in_text(body_text[:500]),
        )
        return True


class SMTPEmailProvider(EmailProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
        msg = EmailMessage()
        msg["From"] = self._settings.smtp_from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        host = self._settings.smtp_host
        port = self._settings.smtp_port
        user = self._settings.smtp_username
        password = self._settings.smtp_password
        use_tls = self._settings.smtp_use_tls

        try:
            if use_tls:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.starttls()
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            return True
        except Exception:
            _log.exception(
                "smtp send failed to=%s host=%s port=%s user=%s",
                to_email,
                host,
                port,
                user or "(none)",
            )
            return False


def get_email_provider(settings: Settings) -> EmailProvider:
    provider = (settings.email_provider or "console").strip().lower()
    if provider == "disabled":
        return DisabledEmailProvider()
    if provider == "smtp":
        return SMTPEmailProvider(settings)
    return ConsoleEmailProvider()


def send_email(
    settings: Settings,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> bool:
    if not to_email or not to_email.strip():
        return False
    provider = get_email_provider(settings)
    return provider.send(
        to_email=to_email.strip(),
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
