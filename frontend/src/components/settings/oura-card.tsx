"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  BatteryLow,
  BatteryMedium,
  CircleDot,
  Link2,
  Loader2,
  RefreshCw,
  Trash2,
  TriangleAlert,
  Unplug,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Section } from "@/components/settings/watch-sources";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ouraConnectUrl,
  useDisconnectOura,
  useOuraStatus,
  useSetRecoverySource,
  useSyncOura,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  historyText,
  lowBattery,
  ouraCardState,
  RECOVERY_SOURCES,
  ringSummary,
  showSourcePicker,
} from "@/lib/oura";
import { cn } from "@/lib/utils";
import type { OuraStatus } from "@/types/api";

/** Motivos conocidos de `?oura=error&motivo=…` (el texto de la URL nunca se enseña tal cual). */
const ERROR_REASONS: Record<string, string> = {
  cancelada: "Has cancelado la autorización en Oura.",
  access_denied: "Has cancelado la autorización en Oura.",
  estado: "La autorización ha caducado. Vuelve a intentarlo.",
  config: "La conexión con Oura no está configurada.",
};

/** Aviso al volver de la web de Oura (`?oura=ok` o `?oura=error&motivo=…`). */
function useOuraReturnToast() {
  const queryClient = useQueryClient();
  const shown = useRef(false);
  useEffect(() => {
    if (shown.current) return;
    const params = new URLSearchParams(window.location.search);
    const result = params.get("oura");
    if (!result) return;
    shown.current = true;
    if (result === "ok")
      toast.success(
        "Oura conectado. Estamos trayendo tu histórico: tardará unos minutos.",
      );
    else
      toast.error(
        ERROR_REASONS[params.get("motivo") ?? ""] ??
          "No se pudo conectar con Oura. Vuelve a intentarlo.",
      );
    void queryClient.invalidateQueries({ queryKey: ["oura-status"] });
    params.delete("oura");
    params.delete("motivo");
    const rest = params.toString();
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${rest ? `?${rest}` : ""}${window.location.hash}`,
    );
  }, [queryClient]);
}

function ConnectButton({ label }: { label: string }) {
  const [busy, setBusy] = useState(false);
  const connect = async () => {
    setBusy(true);
    try {
      const { url } = await ouraConnectUrl();
      if (!url.startsWith("https://")) throw new Error("URL no válida");
      window.location.assign(url);
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : "No se pudo abrir la conexión con Oura.",
      );
      setBusy(false);
    }
  };
  return (
    <Button
      className="min-h-11 w-full sm:w-fit md:min-h-9"
      disabled={busy}
      onClick={connect}
    >
      {busy ? (
        <Loader2 className="animate-spin" aria-hidden />
      ) : (
        <Link2 aria-hidden />
      )}
      {label}
    </Button>
  );
}

/** Selector «Fuente de sueño y recuperación» (solo con reloj y anillo a la vez). */
export function RecoverySourcePicker({ data }: { data: OuraStatus }) {
  const set = useSetRecoverySource();
  if (!showSourcePicker(data)) return null;
  const current = set.isPending ? set.variables : data.recovery_source;
  const hint = RECOVERY_SOURCES.find((s) => s.key === current)?.hint;
  return (
    <fieldset className="space-y-2 rounded-lg border p-3">
      <legend className="px-1 text-sm font-semibold">
        Fuente de sueño y recuperación
      </legend>
      <p className="text-xs text-muted-foreground">
        Tienes reloj y anillo: los dos miden el sueño, la HRV y la FC en reposo.
        Elige de cuál se usan para «Cómo llegas», Progreso → Salud y el plan.
        Tus entrenos siguen llegando del reloj.
      </p>
      <div
        role="radiogroup"
        aria-label="Fuente de sueño y recuperación"
        className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1"
      >
        {RECOVERY_SOURCES.map((s) => (
          <button
            key={s.key}
            type="button"
            role="radio"
            aria-checked={current === s.key}
            disabled={set.isPending}
            onClick={() =>
              current !== s.key &&
              set.mutate(s.key, {
                onSuccess: () => toast.success(`Fuente: ${s.label}.`),
                onError: () => toast.error("No se pudo cambiar la fuente."),
              })
            }
            className={cn(
              "min-h-11 rounded-md px-2 text-sm font-medium transition-colors md:min-h-9",
              current === s.key
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </fieldset>
  );
}

function DisconnectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const disconnect = useDisconnectOura();
  const run = (purge: boolean) =>
    disconnect.mutate(purge, {
      onSuccess: () => {
        toast.success(
          purge
            ? "Oura desconectado y sus datos borrados."
            : "Oura desconectado. Tus datos ya traídos se quedan.",
        );
        onOpenChange(false);
      },
      onError: () => toast.error("No se pudo desconectar Oura."),
    });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Desconectar Oura?</DialogTitle>
          <DialogDescription>
            Dejarán de llegar datos nuevos del anillo. Puedes conservar lo ya
            traído (sueño, recuperación, actividad…) o borrarlo también: borrar
            no se puede deshacer.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            disabled={disconnect.isPending}
            onClick={() => onOpenChange(false)}
          >
            Cancelar
          </Button>
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            disabled={disconnect.isPending}
            onClick={() => run(false)}
          >
            <Unplug aria-hidden /> Desconectar
          </Button>
          <Button
            variant="destructive"
            className="min-h-11 md:min-h-9"
            disabled={disconnect.isPending}
            onClick={() => run(true)}
          >
            {disconnect.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Trash2 aria-hidden />
            )}
            Desconectar y borrar los datos de Oura
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Ring({ data }: { data: OuraStatus }) {
  const ring = data.ring;
  const summary = ringSummary(ring);
  if (!ring || (!summary && ring.battery_level == null && !ring.firmware))
    return null;
  const low = lowBattery(ring);
  const Battery = low ? BatteryLow : BatteryMedium;
  return (
    <div className="space-y-1 rounded-md bg-muted/60 p-3 text-sm">
      {summary && (
        <p className="flex items-center gap-2 font-medium">
          <CircleDot className="size-4 text-klyp-accent" aria-hidden />
          {summary}
        </p>
      )}
      {ring.firmware && (
        <p className="text-xs text-muted-foreground">
          Firmware {ring.firmware}
        </p>
      )}
      {ring.battery_level != null && (
        <p
          className={cn(
            "flex items-center gap-1.5 text-xs",
            low
              ? "text-amber-800 dark:text-amber-300"
              : "text-muted-foreground",
          )}
        >
          <Battery className="size-4 shrink-0" aria-hidden />
          Batería {Math.round(ring.battery_level)} %
          {ring.battery_at && ` · ${formatDateTime(ring.battery_at)}`}
          {low && " · Cárgalo pronto para no perder la noche."}
        </p>
      )}
    </div>
  );
}

/**
 * Conexión con el anillo Oura (OAuth en la web de Oura): estado, importación del histórico,
 * anillo, sincronizar, desconectar (con o sin borrar) y fuente de sueño y recuperación.
 */
export function OuraCard() {
  useOuraReturnToast();
  const { data, isPending, isError, refetch } = useOuraStatus();
  const sync = useSyncOura();
  const [confirm, setConfirm] = useState(false);

  if (isPending) return <Skeleton className="h-40" />;
  if (isError || !data)
    return (
      <div className="space-y-2" role="alert">
        <p className="text-sm text-muted-foreground">
          No se pudo cargar el estado de Oura.
        </p>
        <Button
          variant="outline"
          className="min-h-11"
          onClick={() => refetch()}
        >
          Reintentar
        </Button>
      </div>
    );

  const state = ouraCardState(data);
  const history = historyText(data.history);

  return (
    <div className="space-y-3">
      <Section icon={CircleDot} title="Oura Ring">
        <p className="text-xs text-muted-foreground">
          Trae del anillo tu sueño (fases, hipnograma, FC y HRV de la noche), la
          recuperación (readiness), la temperatura de la piel, el SpO2, el
          estrés y la resiliencia, la actividad y los pasos, y el modo descanso.
          Se abre la web de Oura para que autorices la app: aquí no se escribe
          ni se guarda tu contraseña.
        </p>

        {state === "unconfigured" && (
          <p className="rounded-md bg-muted/60 p-3 text-sm text-muted-foreground">
            Pendiente de configurar por el administrador.
          </p>
        )}

        {state === "disconnected" && <ConnectButton label="Conectar Oura" />}

        {state === "expired" && (
          <>
            <p className="flex items-start gap-2 text-sm text-amber-800 dark:text-amber-300">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              El permiso de Oura ha caducado o se ha retirado: vuelve a conectar
              para seguir recibiendo datos.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <ConnectButton label="Vuelve a conectar" />
              <Button
                variant="ghost"
                className="min-h-11 text-destructive md:min-h-9"
                onClick={() => setConfirm(true)}
              >
                <Trash2 aria-hidden /> Desconectar
              </Button>
            </div>
          </>
        )}

        {state === "connected" && (
          <>
            <p className="text-sm">
              {data.status === "error" ? "Conectado con errores" : "Conectado"}
              {data.last_sync_at
                ? ` · última sincronización ${formatDateTime(data.last_sync_at)}`
                : " · aún sin sincronizar"}
            </p>
            {data.last_error && (
              <p className="text-sm text-destructive">{data.last_error}</p>
            )}
            {history && (
              <p
                className={cn(
                  "flex items-center gap-2 text-xs",
                  data.history.status === "error"
                    ? "text-destructive"
                    : "text-muted-foreground",
                )}
                aria-live="polite"
              >
                {data.history.status === "running" && (
                  <Loader2
                    className="size-3.5 shrink-0 animate-spin"
                    aria-hidden
                  />
                )}
                {history}
              </p>
            )}
            <Ring data={data} />
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                variant="outline"
                className="min-h-11 md:min-h-9"
                disabled={sync.isPending}
                onClick={() =>
                  sync.mutate(undefined, {
                    onSuccess: () =>
                      toast.success(
                        "Sincronizando con Oura: los datos aparecerán en unos minutos.",
                      ),
                    onError: () => toast.error("No se pudo sincronizar."),
                  })
                }
              >
                {sync.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <RefreshCw aria-hidden />
                )}
                Sincronizar ahora
              </Button>
              <Button
                variant="ghost"
                className="min-h-11 text-destructive md:min-h-9"
                onClick={() => setConfirm(true)}
              >
                <Trash2 aria-hidden /> Desconectar
              </Button>
            </div>
          </>
        )}

        {state !== "unconfigured" && (
          <p className="text-xs text-muted-foreground">
            También puedes quitar el acceso desde la app de Oura (Perfil → Datos
            → Apps conectadas) o en cloud.ouraring.com. Si lo haces, aquí verás
            «Vuelve a conectar».
          </p>
        )}
      </Section>

      <RecoverySourcePicker data={data} />
      <DisconnectDialog open={confirm} onOpenChange={setConfirm} />
    </div>
  );
}
