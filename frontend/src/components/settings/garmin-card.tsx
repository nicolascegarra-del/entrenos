"use client";

import {
  CheckCircle2,
  CircleAlert,
  CircleX,
  Loader2,
  RefreshCw,
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
  useSyncNow,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { SyncRun } from "@/types/api";

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

/** Conexión con Garmin y estado de la sincronización (el modo es general: Ajustes → Conexiones). */
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
