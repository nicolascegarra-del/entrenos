import {
  CircleCheck,
  CircleMinus,
  Info,
  OctagonAlert,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Insight, InsightStatus } from "@/types/api";

/** Estados reservados (nunca como color de serie), siempre con icono y texto. */
export const INSIGHT_STATUS: Record<
  InsightStatus,
  { label: string; icon: LucideIcon; className: string }
> = {
  good: {
    label: "Bien",
    icon: CircleCheck,
    className:
      "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200",
  },
  watch: {
    label: "Vigilar",
    icon: TriangleAlert,
    className:
      "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200",
  },
  alert: {
    label: "Atención",
    icon: OctagonAlert,
    className:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200",
  },
  info: {
    label: "Info",
    icon: Info,
    className:
      "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-200",
  },
  nodata: {
    label: "Sin datos",
    icon: CircleMinus,
    className: "border-border bg-muted/60 text-muted-foreground",
  },
};

/** Explicación dinámica de una gráfica: estado, mensaje y fuentes desplegables. */
export function InsightCallout({ insight }: { insight?: Insight }) {
  if (!insight) return null;
  const { label, icon: Icon, className } = INSIGHT_STATUS[insight.status];
  return (
    <div
      className={cn("mt-3 rounded-lg border p-3 text-sm", className)}
      role="note"
    >
      <p className="flex items-start gap-2 font-medium">
        <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          <span className="sr-only">{label}: </span>
          {insight.title}
        </span>
      </p>
      <p className="mt-1 pl-6 opacity-90">{insight.message}</p>
      {insight.evidence.length > 0 && (
        <details className="mt-2 pl-6">
          <summary className="cursor-pointer text-xs font-medium underline-offset-2 hover:underline">
            ¿Por qué? Fuentes
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs opacity-90">
            {insight.evidence.map((e) => (
              <li key={e.label}>
                {e.url ? (
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    {e.label}
                  </a>
                ) : (
                  e.label
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
