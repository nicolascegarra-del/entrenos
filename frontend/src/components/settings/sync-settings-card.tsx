"use client";

import { Hand, Loader2, RefreshCw, Timer } from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSaveSyncSettings, useSyncSettings } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { intervalLabel } from "@/lib/watch-brands";
import { cn } from "@/lib/utils";
import type { SyncMode } from "@/types/api";

const MODES: {
  value: SyncMode;
  label: string;
  description: string;
  icon: typeof Timer;
}[] = [
  {
    value: "auto",
    label: "Automática",
    description:
      "Todas tus conexiones se sincronizan solas cada cierto tiempo.",
    icon: Timer,
  },
  {
    value: "manual",
    label: "Solo manual",
    description: "Solo cuando pulses «Sincronizar ahora» en cada conexión.",
    icon: Hand,
  },
];

/**
 * Sincronización general (automática con intervalo o solo manual) para todas las conexiones: Garmin, COROS,
 * Oura, Suunto, Amazfit, Xiaomi y Samsung. Se guarda al cambiar.
 */
export function SyncSettingsCard() {
  const { data, isPending, isError } = useSyncSettings();
  const save = useSaveSyncSettings();

  const update = (body: { mode: SyncMode; interval_min: number }) =>
    save.mutate(body, {
      onSuccess: (res) =>
        toast.success(
          res.mode === "manual"
            ? "Sincronización solo manual"
            : `Sincronización automática cada ${intervalLabel(res.interval_min)}`,
        ),
      onError: (err) =>
        toast.error(
          err instanceof ApiError ? err.message : "No se pudo guardar.",
        ),
    });

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <RefreshCw className="size-5 text-klyp-accent" aria-hidden />
          Sincronización
        </CardTitle>
        <CardDescription>
          Vale para todas tus conexiones. Los entrenos que llegan solos (Health
          Connect, avisos de Oura) entran al momento igualmente.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-28 w-full" />
        ) : isError || !data ? (
          <p className="text-sm text-destructive">
            No se pudieron cargar las preferencias.
          </p>
        ) : (
          <fieldset className="space-y-3" disabled={save.isPending}>
            <legend className="sr-only">Modo de sincronización</legend>
            <div
              className="grid gap-2 sm:grid-cols-2"
              role="radiogroup"
              aria-label="Modo de sincronización"
            >
              {MODES.map(({ value, label, description, icon: Icon }) => {
                const selected = data.mode === value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() =>
                      !selected &&
                      update({ mode: value, interval_min: data.interval_min })
                    }
                    className={cn(
                      "flex min-h-11 items-start gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                      selected
                        ? "border-klyp-accent bg-klyp-accent/10"
                        : "border-border hover:bg-muted/60",
                    )}
                  >
                    <Icon
                      className={cn(
                        "mt-0.5 size-5 shrink-0",
                        selected ? "text-klyp-accent" : "text-muted-foreground",
                      )}
                      aria-hidden
                    />
                    <span>
                      <span className="block text-sm font-medium">{label}</span>
                      <span className="block text-xs text-muted-foreground">
                        {description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            {data.mode === "auto" && (
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="sync-interval" className="text-sm">
                  Cada
                </label>
                <select
                  id="sync-interval"
                  value={data.interval_min}
                  onChange={(e) =>
                    update({
                      mode: "auto",
                      interval_min: Number(e.target.value),
                    })
                  }
                  className="h-11 rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9"
                >
                  {data.intervals.map((m) => (
                    <option key={m} value={m}>
                      {intervalLabel(m)}
                    </option>
                  ))}
                </select>
                {save.isPending && (
                  <Loader2
                    className="size-4 animate-spin text-muted-foreground"
                    aria-hidden
                  />
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {data.mode === "auto"
                ? `Cada conexión se sincroniza ${intervalLabel(data.interval_min)} después de la anterior.`
                : "La sincronización automática está desactivada."}
            </p>
          </fieldset>
        )}
      </CardContent>
    </Card>
  );
}
