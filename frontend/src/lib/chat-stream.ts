import { authFetch, parseError } from "@/lib/api";
import type { AiProviderId, CoachEffect } from "@/types/api";

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

/**
 * Separa los eventos SSE completos del texto recibido hasta ahora.
 * @param buffer - Texto acumulado (puede acabar a mitad de un evento).
 * @returns Eventos completos y el resto pendiente de más datos.
 */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) });
    } catch {
      // Evento mal formado: se ignora sin romper la conversación.
    }
  }
  return { events, rest };
}

export interface ChatHandlers {
  onMeta?: (meta: {
    conversation_id: number;
    provider: AiProviderId;
    model: string;
  }) => void;
  onDelta: (text: string) => void;
  /** El asistente ha consultado un dato (etiqueta legible). */
  onTool?: (label: string) => void;
  /** El entrenador ha guardado algo en tu ficha o ha propuesto un cambio del plan. */
  onEffect?: (effect: CoachEffect) => void;
}

export interface ChatRequest {
  message: string;
  conversation_id?: number | null;
  provider?: AiProviderId | null;
  /** «interview»: entrevista inicial del entrenador. */
  mode?: "interview" | null;
  /** Repetir la respuesta a la última pregunta (Reintentar / Otra respuesta). */
  regenerate?: boolean;
}

/** El asistente no pudo terminar; si llegó a escribir algo, se guardó como respuesta incompleta. */
export class ChatStreamError extends Error {
  constructor(
    message: string,
    public partialId: number | null = null,
  ) {
    super(message);
  }
}

/** Texto visible mientras llega: oculta las líneas de botones `[[opciones: …]]` (aunque estén a medias). */
export function visibleText(text: string): string {
  return text.replace(/\[\[[\s\S]*?(\]\]|$)/g, "").trimEnd();
}

/**
 * Envía una pregunta al asistente y va entregando la respuesta según llega.
 * @throws ApiError si la API rechaza la petición o el proveedor devuelve un error.
 */
export async function streamChat(
  body: ChatRequest,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await authFetch("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await parseError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  while (!finished) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSse(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "meta") handlers.onMeta?.(data as never);
      else if (event === "delta") handlers.onDelta(String(data.text ?? ""));
      else if (event === "tool") handlers.onTool?.(String(data.label ?? ""));
      else if (event === "effect")
        handlers.onEffect?.(data as unknown as CoachEffect);
      else if (event === "error")
        throw new ChatStreamError(
          String(data.message),
          typeof data.partial_id === "number" ? data.partial_id : null,
        );
      else if (event === "done") finished = true;
    }
  }
}
