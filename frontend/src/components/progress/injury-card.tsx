"use client";

import { INSIGHT_STATUS } from "@/components/progress/insight";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InjuryReport } from "@/types/api";

/** Comprobaciones de riesgo de lesión, cada una con estado (icono + texto) y fuentes. */
export function InjuryCard({ data }: { data: InjuryReport }) {
  const overall = INSIGHT_STATUS[data.status];
  return (
    <div className="space-y-3">
      <p
        className={cn(
          "flex items-center gap-2 rounded-lg border p-3 text-sm font-medium",
          overall.className,
        )}
      >
        <overall.icon className="size-4 shrink-0" aria-hidden />
        <span className="sr-only">{overall.label}: </span>
        {data.summary}
        <span className="ml-auto text-xs font-normal tabular-nums">
          {formatNumber(data.week_km, 1)} km en 7 días
        </span>
      </p>
      <ul className="grid gap-2 md:grid-cols-2">
        {data.checks.map((c) => {
          const st = INSIGHT_STATUS[c.status];
          return (
            <li key={c.key} className="rounded-lg bg-muted/60 p-3">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <st.icon
                  className={cn(
                    "size-4 shrink-0",
                    c.status === "good" && "text-emerald-600",
                    c.status === "watch" && "text-amber-600",
                    c.status === "alert" && "text-red-600",
                  )}
                  aria-hidden
                />
                <span className="sr-only">{st.label}: </span>
                {c.title}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{c.message}</p>
              {c.evidence.length > 0 && (
                <p className="mt-1 text-xs text-muted-foreground/80">
                  {c.evidence.join(" · ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-muted-foreground">{data.disclaimer}</p>
    </div>
  );
}
