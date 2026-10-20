"""
Emails de la app (invitaciones, recuperar contraseña, registro con aprobación) en español,
con versión en texto y en HTML sencillo con la identidad Klyp. Se envían en segundo plano.
"""

from datetime import datetime
from html import escape

from app.core.config import get_settings
from app.core.email import Email, email_enabled

NAVY, ACCENT, GRAY = "#051937", "#2E6DB4", "#6B7280"


def link(path: str) -> str:
    """Enlace absoluto a la web (APP_PUBLIC_URL + ruta)."""
    return get_settings().app_public_url.rstrip("/") + path


def _html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None, footer: str = "") -> str:
    body = "".join(f'<p style="margin:0 0 14px">{escape(p)}</p>' for p in paragraphs)
    if button:
        label, url = button
        body += (
            f'<p style="margin:22px 0"><a href="{escape(url)}" style="background:{ACCENT};color:#fff;'
            f'text-decoration:none;padding:12px 20px;border-radius:8px;display:inline-block;font-weight:600">'
            f"{escape(label)}</a></p>"
            f'<p style="margin:0 0 14px;color:{GRAY};font-size:13px">Si el botón no funciona, copia este enlace: '
            f"{escape(url)}</p>"
        )
    if footer:
        body += f'<p style="margin:18px 0 0;color:{GRAY};font-size:13px">{escape(footer)}</p>'
    return (
        f'<div style="font-family:Inter,Arial,sans-serif;background:#E8EDF5;padding:24px">'
        f'<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden">'
        f'<div style="background:{NAVY};color:#fff;padding:16px 24px;font-weight:600">APP ENTRENOS</div>'
        f'<div style="padding:24px;color:#374151;font-size:15px;line-height:1.5">'
        f'<h1 style="margin:0 0 16px;font-size:20px;color:{NAVY}">{escape(title)}</h1>{body}</div></div></div>'
    )


def _queue(email: Email) -> None:
    from app.tasks.email import send_email_task  # importación diferida: evita el ciclo con Celery

    send_email_task.delay(email.to, email.subject, email.text, email.html)


def _fmt(when: datetime) -> str:
    return when.strftime("%d/%m/%Y")


def send_invitation(to: str, token: str, expires_at: datetime) -> bool:
    """Envía la invitación. Devuelve False si no hay correo configurado."""
    if not email_enabled():
        return False
    url = link(f"/registro?token={token}")
    title = "Te han invitado a APP ENTRENOS"
    text = (
        f"{title}.\n\nCrea tu usuario con este enlace (válido hasta el {_fmt(expires_at)}):\n{url}\n\n"
        "Si no esperabas esta invitación, ignora este email."
    )
    paragraphs = [
        "Te han invitado a APP ENTRENOS para ver y analizar tus entrenamientos de Garmin.",
        f"Crea tu usuario con el botón (el enlace caduca el {_fmt(expires_at)}).",
    ]
    _queue(Email(to, title, text, _html(title, paragraphs, ("Crear mi usuario", url),
                                        "Si no esperabas esta invitación, ignora este email.")))  # fmt: skip
    return True


def send_password_reset(to: str, token: str, minutes: int) -> bool:
    if not email_enabled():
        return False
    url = link(f"/restablecer?token={token}")
    title = "Restablece tu contraseña"
    text = (
        f"Has pedido restablecer tu contraseña de APP ENTRENOS.\n\nUsa este enlace en los próximos {minutes} "
        f"minutos:\n{url}\n\nSi no lo has pedido tú, ignora este email: tu contraseña no cambia."
    )
    paragraphs = [
        "Has pedido restablecer tu contraseña de APP ENTRENOS.",
        f"Pulsa el botón en los próximos {minutes} minutos para elegir una nueva.",
    ]
    footer = "Si no lo has pedido tú, ignora este email: tu contraseña no cambia."
    _queue(Email(to, title, text, _html(title, paragraphs, ("Elegir contraseña nueva", url), footer)))
    return True


def send_approval_request(admins: list[str], applicant: str) -> None:
    """Avisa a los administradores de una solicitud de registro pendiente."""
    if not email_enabled():
        return
    url = link("/admin")
    title = "Nueva solicitud de registro"
    text = f"{applicant} ha pedido una cuenta en APP ENTRENOS.\n\nApruébala o recházala en Admin:\n{url}"
    html = _html(title, [f"{applicant} ha pedido una cuenta en APP ENTRENOS."], ("Revisar en Admin", url))
    for admin in admins:
        _queue(Email(admin, title, text, html))


def send_account_approved(to: str) -> None:
    if not email_enabled():
        return
    url = link("/login")
    title = "Tu cuenta está lista"
    text = f"Un administrador ha aprobado tu cuenta de APP ENTRENOS. Ya puedes entrar:\n{url}"
    _queue(Email(to, title, text, _html(title, ["Un administrador ha aprobado tu cuenta."], ("Entrar", url))))
