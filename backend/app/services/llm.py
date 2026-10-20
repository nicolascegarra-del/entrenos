"""
Capa aislada de proveedores de IA (ChatGPT, Gemini y Claude) sobre sus API REST con httpx.

Cada proveedor es un adaptador con la misma interfaz: `stream_chat` devuelve trozos de
texto a medida que llegan (SSE) y `list_models` comprueba la clave y lista modelos.
Añadir un proveedor = añadir un adaptador. La clave nunca se registra ni aparece en
los mensajes de error.
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from app.models import AiProvider

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(90.0, connect=10.0)
MAX_OUTPUT_TOKENS = 1500


@dataclass(frozen=True)
class ProviderInfo:
    label: str
    default_model: str
    suggested_models: tuple[str, ...]
    keys_url: str
    privacy: str


PROVIDERS: dict[AiProvider, ProviderInfo] = {
    AiProvider.OPENAI: ProviderInfo(
        label="ChatGPT (OpenAI)",
        default_model="gpt-5-mini",
        suggested_models=("gpt-5-mini", "gpt-5", "gpt-4.1-mini"),
        keys_url="https://platform.openai.com/api-keys",
        privacy="Con clave de API, OpenAI no usa tus datos para entrenar sus modelos. Se paga por uso.",
    ),
    AiProvider.GEMINI: ProviderInfo(
        label="Gemini (Google)",
        # Google retira los modelos antiguos para cuentas nuevas aunque sigan en su lista (los 2.5, en 2026).
        default_model="gemini-3.5-flash",
        suggested_models=("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"),
        keys_url="https://aistudio.google.com/app/apikey",
        privacy="Tiene nivel gratuito, pero en él Google puede usar lo que envías para mejorar sus productos. "
        "Con facturación activada, no.",
    ),
    AiProvider.ANTHROPIC: ProviderInfo(
        label="Claude (Anthropic)",
        default_model="claude-haiku-5-5",
        suggested_models=("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"),
        keys_url="https://console.anthropic.com/settings/keys",
        privacy="Con clave de API, Anthropic no usa tus datos para entrenar sus modelos. Se paga por uso.",
    ),
}


class LLMError(Exception):
    """Error del proveedor con un mensaje apto para mostrar al usuario (sin datos sensibles)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message, self.status = message, status


@dataclass
class Chunk:
    """Trozo de respuesta: texto nuevo y, al final, los tokens consumidos (si el proveedor los da)."""

    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


def _provider_detail(body: str, api_key: str = "") -> str:
    """Mensaje de error que da el propio proveedor (JSON `error.message`), recortado y sin la clave."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message", "") if isinstance(error, dict) else ""
    if api_key:
        message = message.replace(api_key, "••••")
    message = " ".join(str(message).split())
    return message[:240] + ("…" if len(message) > 240 else "")


def _error_for(status: int, body: str, api_key: str = "") -> LLMError:
    """Traduce el error HTTP del proveedor a un mensaje claro en español (con su explicación si la da)."""
    lower = body.lower()
    detail = _provider_detail(body, api_key)
    said = f" El proveedor indica: «{detail}»" if detail else ""
    if status in (401, 403) or "api key not valid" in lower or "invalid x-api-key" in lower:
        return LLMError("La clave de API no es válida o no tiene permisos.", status)
    if status == 404 or "model_not_found" in lower or "not found" in lower and "model" in lower:
        return LLMError(f"El modelo no está disponible para tu clave; elige otro en Ajustes.{said}", status)
    if status == 429 or "insufficient_quota" in lower or "credit balance" in lower or "quota" in lower:
        return LLMError("Has superado el límite del proveedor o no te queda saldo en la cuenta.", status)
    if status >= 500:
        return LLMError("El proveedor no está disponible ahora mismo. Inténtalo en un rato.", status)
    return LLMError(f"El proveedor rechazó la petición (código {status}).{said}", status)


def _sse_data(response: httpx.Response) -> Iterator[dict]:
    """Recorre las líneas `data: {...}` de una respuesta SSE."""
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Línea SSE no válida del proveedor de IA")


# ─── Adaptadores ─────────────────────────────────────────────────────────────


def _openai_request(api_key: str, model: str, system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": MAX_OUTPUT_TOKENS * 4,  # los modelos de razonamiento gastan tokens en pensar
    }
    return "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {api_key}"}, body


def _openai_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    for event in events:
        for choice in event.get("choices") or []:
            text = (choice.get("delta") or {}).get("content")
            if text:
                yield Chunk(text=text)
        if usage := event.get("usage"):
            yield Chunk(input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))


def _gemini_request(api_key: str, model: str, system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS * 4},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    return url, {"x-goog-api-key": api_key}, body


def _gemini_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    usage: dict = {}
    for event in events:
        for candidate in event.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("text") and not part.get("thought"):
                    yield Chunk(text=part["text"])
        usage = event.get("usageMetadata") or usage
    if usage:
        yield Chunk(input_tokens=usage.get("promptTokenCount"), output_tokens=usage.get("candidatesTokenCount"))


def _anthropic_request(api_key: str, model: str, system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    body = {"model": model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system, "messages": messages, "stream": True}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return "https://api.anthropic.com/v1/messages", headers, body


def _anthropic_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    input_tokens = output_tokens = None
    for event in events:
        kind = event.get("type")
        if kind == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
            yield Chunk(text=event["delta"]["text"])
        elif kind == "message_start":
            input_tokens = ((event.get("message") or {}).get("usage") or {}).get("input_tokens")
        elif kind == "message_delta":
            output_tokens = (event.get("usage") or {}).get("output_tokens")
        elif kind == "error":
            raise LLMError("El proveedor interrumpió la respuesta. Inténtalo de nuevo.")
    yield Chunk(input_tokens=input_tokens, output_tokens=output_tokens)


_ADAPTERS = {
    AiProvider.OPENAI: (_openai_request, _openai_chunks),
    AiProvider.GEMINI: (_gemini_request, _gemini_chunks),
    AiProvider.ANTHROPIC: (_anthropic_request, _anthropic_chunks),
}


def stream_chat(
    provider: AiProvider,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    client: httpx.Client | None = None,
) -> Iterator[Chunk]:
    """
    Pide una respuesta al proveedor y la devuelve en trozos según llega.

    Args:
        provider: Proveedor configurado por el usuario.
        api_key: Clave de API en claro (solo en memoria durante la petición).
        model: Identificador del modelo.
        system: Instrucciones de sistema con el contexto de los datos del usuario.
        messages: Historial `[{"role": "user"|"assistant", "content": str}]`, el último del usuario.
        client: Cliente httpx (inyectable en tests).

    Raises:
        LLMError: Clave no válida, sin saldo, modelo inexistente o proveedor caído.
    """
    build, parse = _ADAPTERS[provider]
    url, headers, body = build(api_key, model, system, messages)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                raise _error_for(response.status_code, response.read().decode(errors="replace"), api_key)
            yield from parse(_sse_data(response))
    except httpx.TimeoutException as exc:
        raise LLMError("El proveedor tardó demasiado en responder.") from exc
    except httpx.HTTPError as exc:
        raise LLMError("No se pudo conectar con el proveedor de IA.") from exc
    finally:
        if own:
            client.close()


def _keep_chat_model(provider: AiProvider, model_id: str) -> bool:
    """Filtra la lista de modelos a los que sirven para conversar (fuera audio, imagen, embeddings…)."""
    excluded = ("embedding", "audio", "realtime", "tts", "transcribe", "image", "search", "moderation", "dall-e",
                "whisper", "davinci", "babbage", "live", "aqa", "veo", "imagen", "computer-use", "customtools",
                "banana", "omni")  # fmt: skip
    if any(word in model_id for word in excluded):
        return False
    if provider is AiProvider.OPENAI:
        return model_id.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))
    if provider is AiProvider.GEMINI:
        return model_id.startswith("gemini")
    return model_id.startswith("claude")


def list_models(provider: AiProvider, api_key: str, client: httpx.Client | None = None) -> list[str]:
    """
    Comprueba la clave pidiendo la lista de modelos del proveedor.

    Returns:
        Identificadores de modelos de chat, ordenados.

    Raises:
        LLMError: Si la clave no es válida o el proveedor falla.
    """
    if provider is AiProvider.OPENAI:
        url, headers = "https://api.openai.com/v1/models", {"Authorization": f"Bearer {api_key}"}
    elif provider is AiProvider.GEMINI:
        url, headers = (
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            {"x-goog-api-key": api_key},
        )
    else:
        url = "https://api.anthropic.com/v1/models?limit=100"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError("No se pudo conectar con el proveedor de IA.") from exc
    finally:
        if own:
            client.close()
    if response.status_code >= 400:
        raise _error_for(response.status_code, response.text, api_key)
    data = response.json()
    if provider is AiProvider.GEMINI:
        ids = [
            m["name"].removeprefix("models/")
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
    else:
        ids = [m["id"] for m in data.get("data", [])]
    return sorted({m for m in ids if _keep_chat_model(provider, m)}, reverse=True)


def check_model(provider: AiProvider, api_key: str, model: str, client: httpx.Client | None = None) -> None:
    """
    Comprueba que el modelo elegido responde de verdad con una petición mínima.

    Hace falta además de `list_models`: los proveedores siguen listando modelos retirados
    para cuentas nuevas, que luego fallan al usarlos.

    Raises:
        LLMError: Si el modelo no está disponible o la petición falla.
    """
    messages = [{"role": "user", "content": "Responde solo: OK"}]
    for _ in stream_chat(provider, api_key, model, "Prueba de conexión.", messages, client=client):
        pass
