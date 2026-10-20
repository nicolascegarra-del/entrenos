from app.core.email import Email, send_email
from app.tasks.celery_app import celery_app


@celery_app.task(name="email.send", autoretry_for=(OSError,), retry_backoff=30, max_retries=5)
def send_email_task(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Envía un email en segundo plano; reintenta si el servidor SMTP no responde."""
    send_email(Email(to=to, subject=subject, text=text, html=html))
