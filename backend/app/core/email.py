"""
Envío de emails por SMTP genérico (Brevo, Gmail, Resend, el de tu dominio o Mailpit en local).

La configuración sale del panel de administración (Admin → Correo, guardada en BD con la
contraseña cifrada) y, si no hay, de las variables de entorno. Con `EMAIL_BACKEND=file` los
mensajes se guardan como .eml en `STORAGE_DIR/outbox` en vez de enviarse. Nunca se
registra el contenido: puede llevar enlaces de un solo uso.
"""

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.db import engine

logger = logging.getLogger(__name__)

PANEL_KEY = "email.config"  # fila de AppSetting con la configuración del panel (JSON)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True)
class EmailConfig:
    """Configuración efectiva del correo. `source`: panel | env."""

    source: str
    mode: str  # smtp | file | disabled
    host: str = ""
    port: int = 587
    security: str = "starttls"  # starttls | ssl | none
    user: str = ""
    password: str = ""
    sender: str = ""
    public_url: str = "http://localhost:3000"


def panel_config(session: Session) -> dict | None:
    """Configuración guardada desde Admin → Correo (contraseña aún cifrada), o None."""
    from app.models import AppSetting  # diferido: los modelos importan core

    row = session.get(AppSetting, PANEL_KEY)
    if row is None:
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        logger.warning("Configuración de correo del panel no válida; se usa la del entorno")
        return None


def _env_config() -> EmailConfig:
    s = get_settings()
    return EmailConfig(source="env", mode=s.email_mode, host=s.smtp_host, port=s.smtp_port,
                       security=s.smtp_security, user=s.smtp_user, password=s.smtp_password,
                       sender=s.smtp_from, public_url=s.app_public_url)  # fmt: skip


def current_config(session: Session | None = None) -> EmailConfig:
    """
    Configuración efectiva: la del panel si está activada; si no, la del entorno.
    Abre su propia sesión de BD si no recibe una (se usa desde el worker y los servicios).
    """
    try:
        if session is not None:
            data = panel_config(session)
        else:
            with Session(engine) as own:
                data = panel_config(own)
    except SQLAlchemyError:
        data = None
    if not data or not data.get("enabled"):
        return _env_config()
    password = ""
    if data.get("password_enc"):
        try:
            password = decrypt_secret(data["password_enc"])
        except Exception:  # noqa: BLE001 - clave de cifrado cambiada: se trata como sin contraseña
            logger.warning("No se pudo descifrar la contraseña SMTP del panel")
    return EmailConfig(source="panel", mode="smtp", host=data.get("host", ""), port=int(data.get("port", 587)),
                       security=data.get("security", "starttls"), user=data.get("user", ""), password=password,
                       sender=data.get("sender", ""),
                       public_url=data.get("public_url") or get_settings().app_public_url)  # fmt: skip


def email_enabled(session: Session | None = None) -> bool:
    return current_config(session).mode in ("smtp", "file")


def _domain(url: str) -> str:
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return host or "localhost"


def _build(email: Email, config: EmailConfig) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.sender or f"KTrain <no-reply@{_domain(config.public_url)}>"
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Message-ID"] = make_msgid(domain=_domain(config.public_url))
    message.set_content(email.text)
    if email.html:
        message.add_alternative(email.html, subtype="html")
    return message


def smtp_send(message: EmailMessage, config: EmailConfig) -> None:
    """Envía por SMTP. Lanza smtplib.SMTPException u OSError si falla."""
    context = ssl.create_default_context()
    if config.security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(config.host, config.port, timeout=20)
    with server:
        if config.security == "starttls":
            server.starttls(context=context)
        if config.user:
            server.login(config.user, config.password)
        server.send_message(message)


def send_email(email: Email, config: EmailConfig | None = None) -> None:
    """
    Envía (o guarda, con el backend `file`) un email.

    Raises:
        smtplib.SMTPException | OSError: Si el servidor SMTP falla (la tarea Celery reintenta).
    """
    config = config or current_config()
    if config.mode == "disabled":
        logger.warning("Email no enviado: no hay servidor de correo configurado")
        return
    message = _build(email, config)
    if config.mode == "file":
        outbox = Path(get_settings().storage_dir) / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        (outbox / f"{stamp}.eml").write_bytes(message.as_bytes())
        logger.info("Email guardado en la bandeja local")
        return
    smtp_send(message, config)
    logger.info("Email enviado")


def smtp_error_text(exc: Exception) -> str:
    """Explica en español por qué falló el SMTP (sin repetir la contraseña)."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "El servidor rechazó el usuario o la contraseña. Con Gmail hace falta una contraseña de aplicación."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "El servidor no acepta ese remitente: usa una dirección verificada en tu proveedor."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "El servidor rechazó la dirección de destino."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "El servidor no admite esa seguridad: prueba STARTTLS en el puerto 587 o SSL en el 465."
    if isinstance(exc, smtplib.SMTPConnectError | ConnectionRefusedError):
        return "No se pudo conectar con el servidor SMTP: revisa el servidor y el puerto."
    if isinstance(exc, TimeoutError | smtplib.SMTPServerDisconnected):
        return "El servidor SMTP no respondió: revisa el servidor, el puerto y la seguridad (STARTTLS/SSL)."
    if isinstance(exc, ssl.SSLError):
        return "Fallo de cifrado: con el puerto 465 usa SSL y con el 587 usa STARTTLS."
    if isinstance(exc, OSError):
        return "No se pudo conectar con el servidor SMTP: revisa el nombre del servidor y el puerto."
    return "El servidor SMTP devolvió un error al enviar."
