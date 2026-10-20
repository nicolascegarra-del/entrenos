import json

import httpx
import pytest

from app.models import AiProvider
from app.services.llm import LLMError, check_model, list_models, stream_chat


def _sse(*events: dict, done: bool = False) -> bytes:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    if done:
        body += "data: [DONE]\n\n"
    return body.encode()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _collect(provider: AiProvider, handler) -> tuple[str, int | None, int | None]:
    chunks = list(stream_chat(provider, "sk-test-1234", "modelo", "sistema", [{"role": "user", "content": "hola"}],
                              client=_client(handler)))  # fmt: skip
    text = "".join(c.text for c in chunks)
    ins = next((c.input_tokens for c in chunks if c.input_tokens is not None), None)
    outs = next((c.output_tokens for c in chunks if c.output_tokens is not None), None)
    return text, ins, outs


def test_stream_openai_cuando_sse_entonces_texto_y_tokens():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse(
            {"choices": [{"delta": {"content": "Ho"}}]},
            {"choices": [{"delta": {"content": "la"}}]},
            {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 2}},
            done=True,
        ))  # fmt: skip

    assert _collect(AiProvider.OPENAI, handler) == ("Hola", 50, 2)
    assert seen["auth"] == "Bearer sk-test-1234"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sistema"}


def test_stream_gemini_cuando_sse_entonces_ignora_pensamiento_y_mapea_roles():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse(
            {"candidates": [{"content": {"parts": [{"text": "pienso…", "thought": True}]}}]},
            {"candidates": [{"content": {"parts": [{"text": "Respuesta"}]}}],
             "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 5}},
        ))  # fmt: skip

    assert _collect(AiProvider.GEMINI, handler) == ("Respuesta", 30, 5)
    assert seen["key"] == "sk-test-1234"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sistema"
    assert seen["body"]["contents"][0]["role"] == "user"


def test_stream_claude_cuando_sse_entonces_texto_y_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "sk-test-1234"
        assert json.loads(request.content)["system"] == "sistema"
        return httpx.Response(200, content=_sse(
            {"type": "message_start", "message": {"usage": {"input_tokens": 40}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Vale"}},
            {"type": "message_delta", "usage": {"output_tokens": 3}},
        ))  # fmt: skip

    assert _collect(AiProvider.ANTHROPIC, handler) == ("Vale", 40, 3)


@pytest.mark.parametrize(
    ("status", "body", "fragment"),
    [
        (401, "{}", "clave de API no es válida"),
        (429, '{"error": {"code": "insufficient_quota"}}', "saldo"),
        (404, '{"error": "model not found"}', "no está disponible para tu clave"),
        (503, "{}", "no está disponible"),
    ],
)
def test_stream_cuando_error_http_entonces_mensaje_claro_sin_clave(status, body, fragment):
    with pytest.raises(LLMError) as exc:
        _collect(AiProvider.OPENAI, lambda r: httpx.Response(status, content=body.encode()))
    assert fragment in exc.value.message and "sk-test" not in exc.value.message


def test_stream_cuando_no_conecta_entonces_llmerror():
    def handler(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(LLMError, match="No se pudo conectar"):
        _collect(AiProvider.ANTHROPIC, handler)


def test_list_models_cuando_openai_entonces_solo_modelos_de_chat():
    data = {"data": [{"id": "gpt-5-mini"}, {"id": "text-embedding-3-small"}, {"id": "gpt-4o-realtime"},
                     {"id": "o4-mini"}, {"id": "dall-e-3"}]}  # fmt: skip
    models = list_models(AiProvider.OPENAI, "k", client=_client(lambda r: httpx.Response(200, json=data)))
    assert models == ["o4-mini", "gpt-5-mini"]


def test_list_models_cuando_gemini_entonces_filtra_por_generate_content():
    data = {"models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    ]}  # fmt: skip
    models = list_models(AiProvider.GEMINI, "k", client=_client(lambda r: httpx.Response(200, json=data)))
    assert models == ["gemini-2.5-flash"]


def test_list_models_cuando_clave_mala_entonces_llmerror():
    with pytest.raises(LLMError, match="clave"):
        list_models(AiProvider.ANTHROPIC, "k", client=_client(lambda r: httpx.Response(401, json={})))


def test_stream_cuando_modelo_retirado_entonces_muestra_explicacion_del_proveedor():
    # Respuesta real de Google (oct. 2026) para un modelo que sigue en la lista pero ya no se puede usar.
    body = {"error": {"code": 404, "status": "NOT_FOUND", "message": (
        "This model models/gemini-2.5-flash-lite is no longer available to new users. Please update your code "
        "to use models/gemini-3.5-flash-lite for the latest features and improvements."
    )}}  # fmt: skip
    with pytest.raises(LLMError) as exc:
        _collect(AiProvider.GEMINI, lambda r: httpx.Response(404, json=body))
    assert "elige otro en Ajustes" in exc.value.message
    assert "gemini-3.5-flash-lite" in exc.value.message


def test_detalle_del_proveedor_cuando_incluye_la_clave_entonces_la_oculta():
    body = '{"error": {"message": "Key sk-test-1234 is not allowed for this model"}}'
    with pytest.raises(LLMError) as exc:
        _collect(AiProvider.OPENAI, lambda r: httpx.Response(400, content=body.encode()))
    assert "sk-test-1234" not in exc.value.message and "••••" in exc.value.message


def test_check_model_cuando_responde_entonces_ok_y_cuando_falla_entonces_llmerror():
    ok = _client(lambda r: httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "OK"}}]}, done=True)))
    check_model(AiProvider.OPENAI, "k", "gpt-x", client=ok)
    bad = _client(lambda r: httpx.Response(404, json={"error": {"message": "gone"}}))
    with pytest.raises(LLMError, match="gone"):
        check_model(AiProvider.OPENAI, "k", "gpt-x", client=bad)
