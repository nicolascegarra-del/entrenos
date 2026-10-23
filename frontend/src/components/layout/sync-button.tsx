"use client";

import { RefreshCw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useGarminStatus, useSyncNow } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/time-ago";
import { cn } from "@/lib/utils";

/**
 * Sincronizar con Garmin desde cualquier pantalla, con el estado a la vista: cuándo fue la última,
 * si está en curso o si la conexión ha caducado (entonces lleva a Ajustes → Conexiones).
 */
export function SyncButton({ compact = false }: { compact?: boolean }) {
  const { data } = useGarminStatus();
  const sync = useSyncNow();
  if (!data?.connected && data?.connection.status !== "expired") return null;
  if (data.connection.status === "expired")
    return (
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="min-h-11 gap-1.5 text-amber-300 md:min-h-8"
      >
        <Link
          href="/ajustes"
          aria-label="Garmin desconectado: volver a conectar"
        >
          <TriangleAlert className="size-4" aria-hidden />
          {!compact && "Reconectar Garmin"}
        </Link>
      </Button>
    );
  const running = data.last_run?.status === "running" || sync.isPending;
  const last =
    data.last_run?.finished_at ??
    data.last_run?.started_at ??
    data.connection.last_ok_at;
  const failed = data.last_run?.status === "error";
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn("min-h-11 gap-1.5 md:min-h-8", failed && "text-amber-300")}
      disabled={running}
      title={
        failed
          ? "La última sincronización falló"
          : `Última sincronización: ${timeAgo(last)}`
      }
      aria-label={
        running
          ? "Sincronizando con Garmin"
          : `Sincronizar con Garmin (última: ${timeAgo(last)})`
      }
      onClick={() =>
        sync.mutate(undefined, {
          onSuccess: () => toast.success("Sincronizando con Garmin…"),
          onError: (err) =>
            toast.error(
              err instanceof ApiError ? err.message : "No se pudo sincronizar.",
            ),
        })
      }
    >
      <RefreshCw
        className={cn("size-4", running && "animate-spin")}
        aria-hidden
      />
      <span className={cn("text-xs", compact && "sr-only")}>
        {running ? "Sincronizando…" : failed ? "Falló" : timeAgo(last)}
      </span>
    </Button>
  );
}
