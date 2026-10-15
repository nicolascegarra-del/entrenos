"""
Logging estructurado. En producción, una línea JSON por evento con el formato Klyp
({timestamp, level, service, environment, message, request_id…}); en desarrollo, texto legible.

Nunca se registran contraseñas, tokens ni cuerpos de petición: los mensajes que se
emiten en la app ya lo evitan y aquí solo se añaden campos de contexto explícitos.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import get_settings

# Campos extra permitidos en el JSON (se pasan con `logger.info(..., extra={...})`).
_EXTRA_FIELDS = ("request_id", "method", "path", "status", "duration_ms", "user_id", "task")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self.service, self.environment = service, environment

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "environment": self.environment,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            # Traza completa solo en logs internos, nunca en respuestas al cliente.
            payload["error"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str) -> None:
    """Configura el logger raíz una vez por proceso (API, worker o beat)."""
    settings = get_settings()
    level = logging.DEBUG if settings.debug else getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JsonFormatter(f"entrenos-{service}", settings.app_env))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Las librerías HTTP registran URLs con parámetros: solo avisos y errores.
    for noisy in ("httpx", "urllib3", "garminconnect", "garth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
