"""
Mailer utilities (best-effort).

In production configure SMTP via env vars in `config.py`:
- MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_SERVER, MAIL_PORT, MAIL_TLS, MAIL_SSL

If mail is not configured, the function becomes a no-op (security-friendly).
"""

from typing import Optional
import logging

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

from config import get_settings

logger = logging.getLogger(__name__)


def _is_mail_configured(settings) -> bool:
    return bool(settings.MAIL_USERNAME and settings.MAIL_PASSWORD and settings.MAIL_FROM and settings.MAIL_SERVER)


def _get_mail_config(settings) -> ConnectionConfig:
    return ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=int(settings.MAIL_PORT),
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=bool(settings.MAIL_TLS),
        MAIL_SSL_TLS=bool(settings.MAIL_SSL),
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )


async def maybe_send_password_reset_email(
    to_email: str,
    reset_link: str,
    request_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Best-effort: if SMTP isn't configured, do nothing.
    Never raise (password reset flow must remain non-enumerable).
    """
    settings = get_settings()
    if not _is_mail_configured(settings):
        logger.warning("MAIL not configured; skipping password reset email send")
        return

    try:
        fm = FastMail(_get_mail_config(settings))
        subject = f"{settings.APP_NAME} - Reset password"
        ip_txt = f"\n\nIP: {request_ip}" if request_ip else ""
        ua_txt = f"\nUser-Agent: {user_agent}" if user_agent else ""
        body = (
            "Hai richiesto il reset della password.\n\n"
            f"Apri questo link per impostare una nuova password:\n{reset_link}\n"
            "\nSe non sei stato tu, ignora questa email."
            f"{ip_txt}{ua_txt}\n"
        )
        message = MessageSchema(
            subject=subject,
            recipients=[to_email],
            body=body,
            subtype="plain",
        )
        await fm.send_message(message)
    except Exception:
        logger.exception("Failed sending password reset email")
        return

