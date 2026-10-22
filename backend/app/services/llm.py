"""
Capa aislada de proveedores de IA (ChatGPT, Gemini y Claude) sobre sus API REST con httpx.

Cada proveedor es un adaptador con la misma interfaz: `stream_chat` devuelve trozos de
texto a medida que llegan (SSE) y `list_models` comprueba la clave y lista modelos.
Añadir un proveedor = añadir un adaptador. La clave nunca se registra ni aparece en
los mensajes de error.
"""

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx

from app.models import AiProvider

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(90.0, connect=10.0)
MAX_OUTPUT_TOKENS = 3000
MAX_TOOL_ROUNDS = 6  # consultas de datos por pregunta antes de obligar a responder


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


@dataclass(frozen=True)
class ToolSpec:
    """Herramienta que puede llamar el modelo: nombre, para qué sirve y parámetros (JSON Schema)."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Chunk:
    """
    Trozo de respuesta: texto nuevo; `tool` cuando se ha consultado una herramienta (etiqueta para la
    interfaz); y, al final, los tokens consumidos (si el proveedor los da).
    `tool_calls` y `raw` son internos de cada ronda (lo que pidió el modelo).
    """

    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool: str | None = None
    tool_calls: list[ToolCall] | None = None
    raw: object = None


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
#
# Cada adaptador sabe: convertir el historial a su formato (`native`), construir la petición (con las
# herramientas si las hay), leer el streaming (texto + llamadas a herramientas) y añadir al historial
# la ronda de herramientas (lo que pidió el modelo y los resultados) para la siguiente petición.


def _plain_history(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in messages]


# OpenAI (chat completions)


def _openai_tools(tools: list[ToolSpec]) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools]  # fmt: skip


def _openai_request(api_key: str, model: str, system: str, native: list[dict], tools: list[ToolSpec] | None,
                    allow_tools: bool) -> tuple[str, dict, dict]:  # fmt: skip
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *native],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": MAX_OUTPUT_TOKENS * 4,  # los modelos de razonamiento gastan tokens en pensar
    }
    if tools:
        body["tools"] = _openai_tools(tools)
        body["tool_choice"] = "auto" if allow_tools else "none"
    return "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {api_key}"}, body


def _openai_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    calls: dict[int, dict] = {}
    usage: dict = {}
    for event in events:
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                yield Chunk(text=delta["content"])
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["name"] = fn.get("name") or slot["name"]
                slot["arguments"] += fn.get("arguments") or ""
        usage = event.get("usage") or usage
    tool_calls = [ToolCall(c["id"], c["name"], _json_args(c["arguments"])) for _, c in sorted(calls.items())]
    yield Chunk(input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                tool_calls=tool_calls)  # fmt: skip


def _openai_append(native: list[dict], text: str, calls: list[ToolCall], raw, results: list[str]) -> None:
    native.append(
        {
            "role": "assistant",
            "content": text or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)},
                }
                for c in calls
            ],
        }
    )
    for c, result in zip(calls, results, strict=True):
        native.append({"role": "tool", "tool_call_id": c.id, "content": result})


# Gemini


def _gemini_schema(schema: dict) -> dict:
    """Esquema JSON → el subconjunto OpenAPI de Gemini (tipos en mayúsculas)."""
    out = {}
    for key, value in schema.items():
        if key == "type":
            out[key] = str(value).upper()
        elif key == "properties":
            out[key] = {k: _gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _gemini_schema(value)
        elif key in ("description", "enum", "required"):
            out[key] = value
    return out


def _gemini_native(messages: list[dict]) -> list[dict]:
    return [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages]  # fmt: skip


def _gemini_request(api_key: str, model: str, system: str, native: list[dict], tools: list[ToolSpec] | None,
                    allow_tools: bool) -> tuple[str, dict, dict]:  # fmt: skip
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": native,
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS * 4},
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [
            {"name": t.name, "description": t.description, "parameters": _gemini_schema(t.parameters)} for t in tools
        ]}]  # fmt: skip
        body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO" if allow_tools else "NONE"}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    return url, {"x-goog-api-key": api_key}, body


def _gemini_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    usage: dict = {}
    text: list[str] = []
    call_parts: list[dict] = []
    for event in events:
        for candidate in event.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("functionCall"):
                    call_parts.append(part)  # con su `thoughtSignature`: Gemini exige devolverla tal cual
                elif part.get("text") and not part.get("thought"):
                    text.append(part["text"])
                    yield Chunk(text=part["text"])
        usage = event.get("usageMetadata") or usage
    calls = [ToolCall(p["functionCall"].get("id") or p["functionCall"]["name"], p["functionCall"]["name"],
                      p["functionCall"].get("args") or {}) for p in call_parts]  # fmt: skip
    raw = ([{"text": "".join(text)}] if text else []) + call_parts
    yield Chunk(input_tokens=usage.get("promptTokenCount"), output_tokens=usage.get("candidatesTokenCount"),
                tool_calls=calls, raw=raw)  # fmt: skip


def _gemini_append(native: list[dict], text: str, calls: list[ToolCall], raw, results: list[str]) -> None:
    native.append({"role": "model", "parts": raw})
    parts = []
    for c, result in zip(calls, results, strict=True):
        response = {"name": c.name, "response": {"resultado": result}}
        if c.id != c.name:
            response["id"] = c.id
        parts.append({"functionResponse": response})
    native.append({"role": "user", "parts": parts})


# Anthropic (Claude)


def _anthropic_request(api_key: str, model: str, system: str, native: list[dict], tools: list[ToolSpec] | None,
                       allow_tools: bool) -> tuple[str, dict, dict]:  # fmt: skip
    body = {"model": model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system, "messages": native, "stream": True}
    if tools:
        body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        body["tool_choice"] = {"type": "auto" if allow_tools else "none"}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return "https://api.anthropic.com/v1/messages", headers, body


def _anthropic_chunks(events: Iterator[dict]) -> Iterator[Chunk]:
    input_tokens = output_tokens = None
    blocks: dict[int, dict] = {}
    for event in events:
        kind = event.get("type")
        if kind == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                blocks[event.get("index", 0)] = {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "json": "",
                }
            elif block.get("type") == "text":
                blocks[event.get("index", 0)] = {"type": "text", "text": block.get("text") or ""}
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            block = blocks.setdefault(event.get("index", 0), {"type": "text", "text": ""})
            if delta.get("type") == "text_delta":
                block["text"] = block.get("text", "") + delta["text"]
                yield Chunk(text=delta["text"])
            elif delta.get("type") == "input_json_delta":
                block["json"] = block.get("json", "") + (delta.get("partial_json") or "")
        elif kind == "message_start":
            input_tokens = ((event.get("message") or {}).get("usage") or {}).get("input_tokens")
        elif kind == "message_delta":
            output_tokens = (event.get("usage") or {}).get("output_tokens")
        elif kind == "error":
            raise LLMError("El proveedor interrumpió la respuesta. Inténtalo de nuevo.")
    raw, calls = [], []
    for _, b in sorted(blocks.items()):
        if b["type"] == "tool_use":
            args = _json_args(b["json"])
            raw.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": args})
            calls.append(ToolCall(b["id"], b["name"], args))
        elif b.get("text"):
            raw.append({"type": "text", "text": b["text"]})
    yield Chunk(input_tokens=input_tokens, output_tokens=output_tokens, tool_calls=calls, raw=raw)


def _anthropic_append(native: list[dict], text: str, calls: list[ToolCall], raw, results: list[str]) -> None:
    native.append({"role": "assistant", "content": raw})
    native.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": c.id, "content": result}
                                               for c, result in zip(calls, results, strict=True)]})  # fmt: skip


def _json_args(text: str) -> dict:
    try:
        value = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class _Adapter:
    native: Callable[[list[dict]], list[dict]]
    request: Callable[..., tuple[str, dict, dict]]
    chunks: Callable[[Iterator[dict]], Iterator[Chunk]]
    append: Callable[..., None]


_ADAPTERS = {
    AiProvider.OPENAI: _Adapter(_plain_history, _openai_request, _openai_chunks, _openai_append),
    AiProvider.GEMINI: _Adapter(_gemini_native, _gemini_request, _gemini_chunks, _gemini_append),
    AiProvider.ANTHROPIC: _Adapter(_plain_history, _anthropic_request, _anthropic_chunks, _anthropic_append),
}


def _round(client: httpx.Client, adapter: _Adapter, api_key: str, model: str, system: str, native: list[dict],
           tools: list[ToolSpec] | None, allow_tools: bool) -> Iterator[Chunk]:  # fmt: skip
    url, headers, body = adapter.request(api_key, model, system, native, tools, allow_tools)
    with client.stream("POST", url, headers=headers, json=body) as response:
        if response.status_code >= 400:
            raise _error_for(response.status_code, response.read().decode(errors="replace"), api_key)
        yield from adapter.chunks(_sse_data(response))


def stream_chat(
    provider: AiProvider,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    client: httpx.Client | None = None,
    tools: list[ToolSpec] | None = None,
    executor: Callable[[ToolCall], tuple[str, str]] | None = None,
) -> Iterator[Chunk]:
    """
    Pide una respuesta al proveedor y la devuelve en trozos según llega. Con `tools` y `executor`, el modelo
    puede pedir datos: se ejecutan, se le devuelven y se vuelve a preguntar (hasta MAX_TOOL_ROUNDS rondas;
    en la última ya no puede pedir más y debe responder).

    Args:
        provider: Proveedor configurado por el usuario.
        api_key: Clave de API en claro (solo en memoria durante la petición).
        model: Identificador del modelo.
        system: Instrucciones de sistema con el contexto de los datos del usuario.
        messages: Historial `[{"role": "user"|"assistant", "content": str}]`, el último del usuario.
        client: Cliente httpx (inyectable en tests).
        tools: Herramientas que puede usar el modelo.
        executor: Ejecuta una llamada y devuelve (etiqueta para la interfaz, resultado para el modelo).

    Yields:
        Trozos de texto; `Chunk(tool=…)` cada vez que se consulta una herramienta; al final, los tokens
        sumados de todas las rondas.

    Raises:
        LLMError: Clave no válida, sin saldo, modelo inexistente o proveedor caído.
    """
    adapter = _ADAPTERS[provider]
    native = adapter.native(messages)
    use_tools = tools if tools and executor else None
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    total_in = total_out = None
    try:
        for n in range(MAX_TOOL_ROUNDS + 1):
            allow = bool(use_tools) and n < MAX_TOOL_ROUNDS
            text: list[str] = []
            last = Chunk()
            for chunk in _round(client, adapter, api_key, model, system, native, use_tools, allow):
                if chunk.text:
                    text.append(chunk.text)
                    yield chunk
                else:
                    last = chunk
            if last.input_tokens is not None:
                total_in = (total_in or 0) + last.input_tokens
            if last.output_tokens is not None:
                total_out = (total_out or 0) + last.output_tokens
            calls = (last.tool_calls or []) if allow else []
            if not calls:
                break
            if text:
                yield Chunk(text="\n\n")  # separa lo que dijo antes de consultar de lo siguiente
            results = []
            for call in calls:
                label, result = executor(call)  # type: ignore[misc]
                yield Chunk(tool=label)
                results.append(result)
            adapter.append(native, "".join(text), calls, last.raw, results)
        yield Chunk(input_tokens=total_in, output_tokens=total_out)
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
