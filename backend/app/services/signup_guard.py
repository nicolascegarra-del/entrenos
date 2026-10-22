"""
Barreras del autoregistro: emails desechables (lista empaquetada + lista extra del
administrador) y captcha de Cloudflare Turnstile.
"""

import logging
from functools import lru_cache
from pathlib import Path

import httpx
from sqlmodel import Session

from app.core.config import get_settings
from app.services.accounts import get_setting

logger = logging.getLogger(__name__)

DOMAINS_FILE = Path(__file__).resolve().parent.parent / "data" / "disposable_domains.txt"
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


@lru_cache
def _bundled_domains() -> frozenset[str]:
    lines = DOMAINS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


def parse_domains(text: str) -> list[str]:
    """Normaliza una lista escrita a mano (comas, espacios o líneas; sin «@»)."""
    parts = text.replace(",", "\n").split()
    return sorted({p.strip().lower().lstrip("@") for p in parts if "." in p})


def extra_domains(session: Session) -> list[str]:
    return parse_domains(get_setting(session, "blocked_domains", ""))


def is_blocked_email(session: Session, email: str) -> bool:
    """True si el dominio (o uno de sus dominios padre) es desechable o está bloqueado."""
    domain = email.rsplit("@", 1)[-1].lower()
    blocked = _bundled_domains() | set(extra_domains(session))
    labels = domain.split(".")
    return any(".".join(labels[i:]) in blocked for i in range(len(labels) - 1))


def captcha_enabled() -> bool:
    settings = get_settings()
    return bool(settings.turnstile_site_key and settings.turnstile_secret_key)


def verify_captcha(token: str | None, remote_ip: str | None, client: httpx.Client | None = None) -> bool:
    """
    Comprueba el token de Turnstile con Cloudflare. Sin captcha configurado, siempre True.
    Si Cloudflare no responde, se rechaza (mejor reintentar que dejar pasar bots).
    """
    if not captcha_enabled():
        return True
    if not token:
        return False
    data = {"secret": get_settings().turnstile_secret_key, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(10.0))
    try:
        response = client.post(TURNSTILE_URL, data=data)
        return response.status_code == 200 and bool(response.json().get("success"))
    except (httpx.HTTPError, ValueError):
        logger.warning("No se pudo verificar el captcha con Cloudflare")
        return False
    finally:
        if own:
            client.close()
