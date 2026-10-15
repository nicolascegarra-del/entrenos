"""Formato de error estándar Klyp: {"error": {"code", "message", "request_id"}}."""

import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


def _error(status: int, code: str, message: str, request_id: str, field: str | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": message, "request_id": request_id}
    if field:
        body["field"] = field
    return JSONResponse(status_code=status, content={"error": body})


def register_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path != "/health":  # el healthcheck cada 30 s solo sería ruido
            # Solo método y ruta: la query puede llevar tokens (p. ej. invitaciones).
            access_logger.info(
                "%s %s %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
        return response

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        return _error(exc.status_code, code, str(exc.detail), request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or None
        if first.get("type") == "value_error":
            # Validaciones propias (ValueError en español): se muestran tal cual.
            message = str(first.get("msg", "")).removeprefix("Value error, ")
        else:
            message = f"El campo {field} no es válido." if field else "Datos no válidos."
        return _error(422, "VALIDATION_ERROR", message, request.state.request_id, field)

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        logger.exception("Error no controlado", extra={"request_id": request.state.request_id})
        return _error(500, "INTERNAL_ERROR", "Error interno del servidor.", request.state.request_id)
