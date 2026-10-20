"""
Envío de emails por SMTP genérico (Brevo, Resend, el de tu dominio o Mailpit en local).

Con `EMAIL_BACKEND=file` los mensajes se guardan como .eml en `STORAGE_DIR/outbox` en vez
de enviarse (útil sin servidor de correo). Nunca se registra el contenido: puede llevar
enlaces de un solo uso.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None


def email_enabled() -> bool:
    return get_settings().email_mode in ("smtp", "file")


def _build(email: Email) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from or f"APP ENTRENOS <no-reply@{_domain(settings.app_public_url)}>"
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Message-ID"] = make_msgid(domain=_domain(settings.app_public_url))
    message.set_content(email.text)
    if email.html:
        message.add_alternative(email.html, subtype="html")
    return message


def _domain(url: str) -> str:
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return host or "localhost"


def send_email(email: Email) -> None:
    """
    Envía (o guarda, con el backend `file`) un email.

    Raises:
        smtplib.SMTPException | OSError: Si el servidor SMTP falla (la tarea Celery reintenta).
    """
    settings = get_settings()
    mode = settings.email_mode
    if mode == "disabled":
        logger.warning("Email no enviado: no hay servidor de correo configurado")
        return
    message = _build(email)
    if mode == "file":
        outbox = Path(settings.storage_dir) / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        (outbox / f"{stamp}.eml").write_bytes(message.as_bytes())
        logger.info("Email guardado en la bandeja local")
        return
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    with server:
        if settings.smtp_security == "starttls":
            server.starttls(context=context)
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
    logger.info("Email enviado")
