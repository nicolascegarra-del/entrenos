"use client";

import { useState } from "react";

import { formatClock, formatHm, hourTicks } from "@/lib/oura";
import { cn } from "@/lib/utils";

export interface Band {
  /** Carril en el que va (para el hipnograma, la fase). */
  lane: string;
  start: number;
  end: number;
  label: string;
  className: string;
}

/**
 * Franjas de tiempo por carriles con eje de hora: el hipnograma (un carril por fase, de despierto
 * a profundo) y el perfil de actividad cada 5 min (un solo carril). Al pasar el dedo o el ratón
 * por un tramo se ve su fase y su hora; la leyenda y los nombres de los carriles evitan que el
 * color sea la única pista.
 */
export function TimeBands({
  lanes,
  bands,
  ariaLabel,
  laneHeight = "h-8",
  showLaneLabels = true,
}: {
  lanes: { key: string; label: string }[];
  bands: Band[];
  ariaLabel: string;
  laneHeight?: string;
  showLaneLabels?: boolean;
}) {
  const [active, setActive] = useState<Band | null>(null);
  if (!bands.length) return null;
  const min = Math.min(...bands.map((b) => b.start));
  const max = Math.max(...bands.map((b) => b.end));
  const span = max - min || 1;
  const pct = (t: number) => ((t - min) / span) * 100;
  const hours = span / 3_600_000;
  const ticks = hourTicks(min, max, hours > 14 ? 3 : hours > 8 ? 2 : 1);

  return (
    <figure className="space-y-1">
      <div className="flex gap-2">
        {showLaneLabels && (
          <div className="flex w-16 shrink-0 flex-col text-[11px] text-muted-foreground sm:w-20">
            {lanes.map((l) => (
              <span key={l.key} className={cn("flex items-center", laneHeight)}>
                {l.label}
              </span>
            ))}
          </div>
        )}
        <div
          className="relative min-w-0 flex-1 rounded-md bg-muted/40"
          role="img"
          aria-label={ariaLabel}
          onPointerLeave={() => setActive(null)}
        >
          {lanes.map((l, i) => (
            <div
              key={l.key}
              className={cn(
                laneHeight,
                i > 0 && "border-t border-dashed border-border",
              )}
            />
          ))}
          {bands.map((b) => {
            const lane = Math.max(
              0,
              lanes.findIndex((l) => l.key === b.lane),
            );
            return (
              <div
                key={`${b.lane}-${b.start}`}
                className={cn(
                  "absolute rounded-[2px] transition-opacity",
                  b.className,
                  active && active !== b && "opacity-60",
                )}
                style={{
                  left: `${pct(b.start)}%`,
                  width: `max(${pct(b.end) - pct(b.start)}%, 1px)`,
                  top: `calc(${(lane / lanes.length) * 100}% + 2px)`,
                  height: `calc(${100 / lanes.length}% - 4px)`,
                }}
                onPointerEnter={() => setActive(b)}
                onClick={() => setActive(b)}
              />
            );
          })}
        </div>
      </div>
      <div className={cn("relative h-4", showLaneLabels && "ml-18 sm:ml-22")}>
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute -translate-x-1/2 text-[11px] text-muted-foreground tabular-nums"
            style={{ left: `${pct(t)}%` }}
          >
            {formatClock(t)}
          </span>
        ))}
      </div>
      <figcaption
        className="min-h-5 text-xs text-muted-foreground"
        aria-live="polite"
      >
        {active
          ? `${active.label} · ${formatClock(active.start)}–${formatClock(active.end)} · ${formatHm((active.end - active.start) / 1000)}`
          : "Toca o pasa el ratón por un tramo para ver la hora."}
      </figcaption>
    </figure>
  );
}

/** Leyenda de colores con su nombre (la identidad nunca va solo en el color). */
export function BandLegend({
  items,
}: {
  items: { key: string; label: string; className: string; sub?: string }[];
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <span
            className={cn("size-3 shrink-0 rounded-sm", i.className)}
            aria-hidden
          />
          {i.label}
          {i.sub && (
            <span className="text-muted-foreground tabular-nums">{i.sub}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
