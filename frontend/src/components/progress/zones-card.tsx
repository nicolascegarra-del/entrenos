"use client";

import { Info } from "lucide-react";

import { formatDate, formatDuration } from "@/lib/format";
import { thresholdAlternatives, type ThresholdSource } from "@/lib/thresholds";
import type { ZoneSet, ZonesReport } from "@/types/api";

const LTHR_SOURCE = {
  test: "la de tu último test confirmado (manda durante 8 semanas)",
  garmin: "la última que calculó Garmin",
  fc_max: "estimada como el 89 % de tu FC máxima",
} as const;

const PACE_SOURCE = {
  test: "tu último test confirmado (manda durante 8 semanas sobre Garmin y las estimaciones)",
  garmin: "el umbral de lactato que calcula tu reloj Garmin",
  vdot: "ritmo umbral (T) de Daniels según tu nivel de carrera",
  velocidad_critica: "estimado a partir de tu velocidad crítica",
  mejor_hora:
    "tu mejor hora de carrera: el umbral es, como mínimo, el ritmo que ya aguantas 60 min",
} as const;

function paceRange(fast: number | null, slow: number | null): string {
  // `fast` es el límite rápido de la zona y `slow` el lento; sin límite lento = «más lento de».
  if (slow == null && fast != null)
    return `más lento de ${formatDuration(fast)}`;
  if (fast == null && slow != null)
    return `más rápido de ${formatDuration(slow)}`;
  return `${formatDuration(fast)}–${formatDuration(slow)}`;
}

/** Diferencia legible entre el umbral nuevo y el anterior («+3 ppm», «8 s/km más rápido»). */
export function zonesChange(current: ZoneSet, previous: ZoneSet): string[] {
  const out: string[] = [];
  const a = previous.thresholds;
  const b = current.thresholds;
  if (a.lthr != null && b.lthr != null && a.lthr !== b.lthr)
    out.push(
      `FC umbral ${b.lthr > a.lthr ? "+" : "−"}${Math.abs(b.lthr - a.lthr)} ppm`,
    );
  if (
    a.threshold_pace_s_km != null &&
    b.threshold_pace_s_km != null &&
    a.threshold_pace_s_km !== b.threshold_pace_s_km
  ) {
    const diff = a.threshold_pace_s_km - b.threshold_pace_s_km;
    out.push(
      `ritmo umbral ${Math.abs(diff)} s/km ${diff > 0 ? "más rápido" : "más lento"}`,
    );
  }
  return out;
}

function Alternatives({
  candidates,
  chosen,
}: {
  candidates?: Partial<Record<ThresholdSource, number>>;
  chosen?: ThresholdSource | null;
}) {
  const items = thresholdAlternatives(candidates, chosen);
  if (items.length < 2) return null;
  return (
    <details className="mb-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer">
        Otras estimaciones del umbral
      </summary>
      <ul className="mt-1 space-y-0.5 tabular-nums">
        {items.map((a) => (
          <li
            key={a.key}
            className={a.chosen ? "font-medium text-foreground" : ""}
          >
            {a.label}: {a.pace}
            {a.chosen ? " (la que se usa)" : ""}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Umbrales y zonas de FC y ritmo (Friel), con aviso cuando han cambiado. */
export function ZonesCard({ data }: { data: ZonesReport }) {
  const z = data.current;
  if (!z)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Aún no hay datos suficientes para calcular tus zonas.
      </p>
    );
  const t = z.thresholds;
  return (
    <div className="space-y-4">
      {data.changed_recently && data.previous && (
        <p
          role="status"
          className="flex items-start gap-2 rounded-lg border border-sky-300 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-200"
        >
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <strong>Tus zonas han cambiado</strong> el{" "}
            {formatDate(`${z.valid_from}T12:00:00`)}:{" "}
            {zonesChange(z, data.previous).join(" · ")}. Los ritmos del plan y
            los análisis ya usan las nuevas.
          </span>
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {z.zones.hr.length > 0 && (
          <div>
            <p className="text-sm font-medium">
              Zonas de pulso · FC umbral {t.lthr} ppm
            </p>
            <p className="mb-2 text-xs text-muted-foreground">
              {t.lthr_source ? LTHR_SOURCE[t.lthr_source] : ""}
            </p>
            <table className="w-full text-sm tabular-nums">
              <caption className="sr-only">
                Zonas de frecuencia cardiaca
              </caption>
              <tbody>
                {z.zones.hr.map((row) => (
                  <tr key={row.name} className="border-t">
                    <td className="py-1.5 pr-2">{row.name}</td>
                    <td className="py-1.5 text-right">
                      {row.max == null
                        ? `≥ ${row.min}`
                        : row.min === 0
                          ? `< ${row.max + 1}`
                          : `${row.min}–${row.max}`}{" "}
                      ppm
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {z.zones.pace.length > 0 && t.threshold_pace_s_km && (
          <div>
            <p className="text-sm font-medium">
              Zonas de ritmo · umbral {formatDuration(t.threshold_pace_s_km)}{" "}
              /km
            </p>
            <p className="mb-2 text-xs text-muted-foreground">
              {t.pace_source ? PACE_SOURCE[t.pace_source] : ""}
            </p>
            <Alternatives candidates={t.candidates} chosen={t.pace_source} />
            <table className="w-full text-sm tabular-nums">
              <caption className="sr-only">Zonas de ritmo</caption>
              <tbody>
                {z.zones.pace.map((row) => (
                  <tr key={row.name} className="border-t">
                    <td className="py-1.5 pr-2">{row.name}</td>
                    <td className="py-1.5 text-right">
                      {paceRange(row.fast, row.slow)} /km
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Vigentes desde el {formatDate(`${z.valid_from}T12:00:00`)}. Se
        recalculan solas tras cada sincronización cuando cambia tu umbral (zonas
        de Friel).
      </p>
    </div>
  );
}
