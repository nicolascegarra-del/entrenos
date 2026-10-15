import json
import logging

from app.core.logging import JsonFormatter


def _record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord("app.access", logging.INFO, __file__, 1, msg, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_cuando_peticion_entonces_formato_klyp_con_contexto():
    line = JsonFormatter("entrenos-api", "production").format(
        _record("GET /api/v1/goals 200", request_id="req_abc", status=200, duration_ms=12)
    )
    data = json.loads(line)
    assert data["level"] == "INFO" and data["service"] == "entrenos-api"
    assert data["environment"] == "production" and data["message"] == "GET /api/v1/goals 200"
    assert data["request_id"] == "req_abc" and data["status"] == 200
    assert data["timestamp"].endswith("+00:00")


def test_json_formatter_cuando_campos_no_permitidos_entonces_no_se_registran():
    data = json.loads(JsonFormatter("entrenos-api", "production").format(_record("login", password="secreta")))
    assert "password" not in data and "secreta" not in json.dumps(data)


def test_json_formatter_cuando_excepcion_entonces_tipo_y_traza_solo_en_log():
    try:
        raise ValueError("fallo")
    except ValueError:
        import sys

        record = logging.LogRecord("app", logging.ERROR, __file__, 1, "Error no controlado", (), sys.exc_info())
    data = json.loads(JsonFormatter("entrenos-api", "production").format(record))
    assert data["error"] == "ValueError" and "Traceback" in data["traceback"]
