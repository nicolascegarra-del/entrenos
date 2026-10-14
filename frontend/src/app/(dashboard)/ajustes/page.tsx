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
import { useGarminStatus, useSyncNow } from "@/hooks/use-api";
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

function GarminCard() {
  const { data, isPending, isError, refetch } = useGarminStatus();
  const sync = useSyncNow();

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
          <CardDescription>Se sincroniza solo cada 30 minutos.</CardDescription>
        </div>
        {data.connected ? (
          <Badge className="gap-1 bg-emerald-600 text-white hover:bg-emerald-600">
            <CheckCircle2 className="size-3" aria-hidden /> Conectado
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
          </>
        ) : (
          <div className="space-y-2 text-sm">
            <p>Para conectar tu cuenta, ejecuta en el servidor:</p>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">
              docker compose exec api python -m app.cli garmin-login
            </pre>
            <p className="text-muted-foreground">
              La contraseña de Garmin no se guarda: solo los tokens de sesión.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AjustesPage() {
  return (
    <section className="space-y-4">
      <h1 className="font-heading text-2xl font-bold md:text-3xl">Ajustes</h1>
      <div className="max-w-2xl">
        <GarminCard />
      </div>
    </section>
  );
}
