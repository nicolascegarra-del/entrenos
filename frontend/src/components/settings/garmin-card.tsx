"use client";

import {
  CheckCircle2,
  CircleAlert,
  CircleX,
  Hand,
  Loader2,
  RefreshCw,
  Timer,
  Watch,
} from "lucide-react";
import { toast } from "sonner";

import { GarminConnectForm } from "@/components/settings/garmin-connect-form";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDisconnectGarmin,
  useGarminStatus,
  useSaveSyncSettings,
  useSyncNow,
  useSyncSettings,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SyncMode, SyncRun } from "@/types/api";

function LastRun({ run }: { run: SyncRun }) {
  if (run.status === "running") {
    return (
      <p className="flex items-center gap-2 text-sm" role="status">
        <Loader2 className="size-4 animate-spin text-klyp-accent" aria-hidden />{" "}
        Sincronizando…
      </p>
    );
  }
  const ok = run.status === "success";
  return (
    <div className="space-y-1 text-sm">
      <p className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2
            className="size-4 text-emerald-600 dark:text-emerald-400"
            aria-hidden
          />
        ) : (
          <CircleAlert className="size-4 text-destructive" aria-hidden />
        )}
        <span className="font-medium">
          {ok
            ? "Última sincronización correcta"
            : "La última sincronización falló"}
        </span>
      </p>
      <p className="text-muted-foreground">
        {formatDateTime(run.finished_at ?? run.started_at)}
        {ok &&
          ` · ${run.new_activities} actividades nuevas · ${run.daily_days} días de métricas`}
      </p>
      {!ok && run.error && <p className="text-muted-foreground">{run.error}</p>}
    </div>
  );
}

/** "15 min", "1 h", "24 h"… */
function intervalLabel(minutes: number): string {
  return minutes < 60 ? `${minutes} min` : `${minutes / 60} h`;
}

const MODES: {
  value: SyncMode;
  label: string;
  description: string;
  icon: typeof Timer;
}[] = [
  {
    value: "auto",
    label: "Automática",
    description: "Sincroniza sola cada cierto tiempo.",
    icon: Timer,
  },
  {
    value: "manual",
    label: "Solo manual",
    description: "Solo cuando pulses «Sincronizar ahora».",
    icon: Hand,
  },
];

/** Modo de sincronización (automática con intervalo o solo manual). Se guarda al cambiar. */
function SyncModeControl() {
  const { data, isPending, isError } = useSyncSettings();
  const save = useSaveSyncSettings();
  if (isPending) return <Skeleton className="h-28 w-full" />;
  if (isError)
    return (
      <p className="text-sm text-destructive">
        No se pudieron cargar las preferencias.
      </p>
    );

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
    <fieldset className="space-y-3" disabled={save.isPending}>
      <legend className="mb-2 text-sm font-medium">Sincronización</legend>
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
              update({ mode: "auto", interval_min: Number(e.target.value) })
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
        {data.next_sync_at
          ? `Próxima sincronización automática: ${formatDateTime(data.next_sync_at)} (aprox.)`
          : "La sincronización automática está desactivada."}
      </p>
    </fieldset>
  );
}

/** Conexión con Garmin, estado de la sincronización y modo (automático o manual). */
export function GarminCard() {
  const { data, isPending, isError, refetch } = useGarminStatus();
  const sync = useSyncNow();
  const disconnect = useDisconnectGarmin();

  if (isPending) return <Skeleton className="h-44 w-full" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudo consultar el estado de Garmin."
        onRetry={() => refetch()}
      />
    );

  const running = data.last_run?.status === "running" || sync.isPending;
  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 font-heading text-lg">
            <Watch className="size-5 text-klyp-accent" aria-hidden /> Garmin
            Connect
          </CardTitle>
          <CardDescription>
            Actividades y métricas diarias de tu reloj.
          </CardDescription>
        </div>
        {data.connected ? (
          <Badge className="gap-1 bg-emerald-600 text-white hover:bg-emerald-600">
            <CheckCircle2 className="size-3" aria-hidden /> Conectado
          </Badge>
        ) : data.connection.status === "expired" ? (
          <Badge
            variant="outline"
            className="gap-1 border-amber-500 text-amber-700 dark:text-amber-300"
          >
            <CircleAlert className="size-3" aria-hidden /> Caducada
          </Badge>
        ) : (
          <Badge variant="outline" className="gap-1">
            <CircleX className="size-3" aria-hidden /> Sin conectar
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {data.connected ? (
          <>
            {data.last_run ? (
              <LastRun run={data.last_run} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Aún no se ha sincronizado.
              </p>
            )}
            <Button
              className="min-h-11 w-full sm:w-auto"
              disabled={running}
              onClick={() =>
                sync.mutate(undefined, {
                  onError: (err) =>
                    toast.error(
                      err instanceof ApiError
                        ? err.message
                        : "No se pudo sincronizar.",
                    ),
                })
              }
            >
              {running ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <RefreshCw aria-hidden />
              )}
              Sincronizar ahora
            </Button>
            <div className="border-t border-border pt-4">
              <SyncModeControl />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4 text-sm">
              <span className="text-muted-foreground">
                {data.connection.display_name
                  ? `Cuenta: ${data.connection.display_name}`
                  : "Cuenta de Garmin conectada"}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 text-destructive md:min-h-8"
                disabled={disconnect.isPending}
                onClick={() => {
                  if (
                    !window.confirm(
                      "¿Desconectar Garmin? Se borran los tokens; tus actividades se quedan.",
                    )
                  )
                    return;
                  disconnect.mutate(undefined, {
                    onSuccess: () => toast.success("Garmin desconectado"),
                  });
                }}
              >
                Desconectar
              </Button>
            </div>
          </>
        ) : (
          <GarminConnectForm reconnect={data.connection.status === "expired"} />
        )}
      </CardContent>
    </Card>
  );
}
