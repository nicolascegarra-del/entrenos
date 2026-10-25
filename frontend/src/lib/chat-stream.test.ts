import { describe, expect, it } from "vitest";

import { toBlocks } from "@/components/assistant/markdown";

import { parseSse, visibleText } from "./chat-stream";

describe("parseSse", () => {
  it("separa eventos completos y guarda el resto", () => {
    const { events, rest } = parseSse(
      'event: meta\ndata: {"conversation_id": 3}\n\nevent: delta\ndata: {"text": "Ho"}\n\nevent: del',
    );
    expect(events).toEqual([
      { event: "meta", data: { conversation_id: 3 } },
      { event: "delta", data: { text: "Ho" } },
    ]);
    expect(rest).toBe("event: del");
  });

  it("une trozos que llegan partidos", () => {
    const first = parseSse('event: delta\ndata: {"te');
    expect(first.events).toEqual([]);
    const second = parseSse(first.rest + 'xt": "la"}\n\n');
    expect(second.events[0].data).toEqual({ text: "la" });
  });

  it("ignora eventos mal formados y acepta CRLF", () => {
    const { events } = parseSse(
      "event: delta\r\ndata: {roto\r\n\r\nevent: done\r\ndata: {}\r\n\r\n",
    );
    expect(events).toEqual([{ event: "done", data: {} }]);
  });
});

describe("toBlocks (Markdown del asistente)", () => {
  it("agrupa párrafos, listas y títulos", () => {
    const blocks = toBlocks(
      "## Hoy\nEstás fresco.\nSigue así.\n\n- Rodaje suave\n- Estiramientos\n1. Uno\n2. Dos",
    );
    expect(blocks).toEqual([
      { kind: "h", text: "Hoy" },
      { kind: "p", lines: ["Estás fresco.", "Sigue así."] },
      { kind: "ul", items: ["Rodaje suave", "Estiramientos"] },
      { kind: "ol", items: ["Uno", "Dos"] },
    ]);
  });
});

describe("eventos de consulta del asistente", () => {
  it("el evento tool trae la etiqueta de lo consultado", () => {
    const { events } = parseSse(
      'event: tool\ndata: {"label": "Tus zonas y umbrales"}\n\n',
    );
    expect(events).toEqual([
      { event: "tool", data: { label: "Tus zonas y umbrales" } },
    ]);
  });
});

describe("visibleText", () => {
  it("oculta las líneas de botones, también a medio llegar", () => {
    expect(visibleText("¿Qué carrera?\n[[opciones: 5K | 10K]]")).toBe(
      "¿Qué carrera?",
    );
    expect(visibleText("¿Qué carrera?\n[[opciones: 5K | 1")).toBe(
      "¿Qué carrera?",
    );
    expect(visibleText("Texto normal")).toBe("Texto normal");
  });
});
