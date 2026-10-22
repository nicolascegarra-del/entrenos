"use client";

import { Database, Loader2 } from "lucide-react";

/** «Ha consultado 1 dato» / «Ha consultado 3 datos». */
export function consultedSummary(count: number): string {
  return `Ha consultado ${count} ${count === 1 ? "dato" : "datos"}`;
}

/**
 * Datos que ha consultado el asistente para responder (herramientas). Mientras piensa, muestra la última
 * consulta en curso; después, la lista plegable.
 */
export function Consulted({
  labels,
  working,
}: {
  labels: string[];
  working: boolean;
}) {
  if (!labels.length && !working) return null;
  if (working)
    return (
      <p
        className="mb-1 flex items-center gap-2 text-xs text-muted-foreground"
        role="status"
      >
        <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
        {labels.length
          ? `Consultando: ${labels[labels.length - 1]}…`
          : "Pensando…"}
      </p>
    );
  return (
    <details className="mb-1 text-xs text-muted-foreground">
      <summary className="flex min-h-8 cursor-pointer list-none items-center gap-1.5">
        <Database className="size-3.5 shrink-0" aria-hidden />
        {consultedSummary(labels.length)}
      </summary>
      <ul className="mt-1 flex flex-wrap gap-1">
        {labels.map((l, i) => (
          <li
            key={`${i}-${l}`}
            className="rounded-full border bg-background px-2 py-0.5"
          >
            {l}
          </li>
        ))}
      </ul>
    </details>
  );
}
