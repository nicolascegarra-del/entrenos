"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, Link2, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Section } from "@/components/settings/watch-sources";
import { Button } from "@/components/ui/button";
import { useSyncCorosOfficial } from "@/hooks/use-api";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { SourcesStatus } from "@/types/api";

const RESULT: Record<string, [boolean, string]> = {
  ok: [true, "COROS conectado: ya puedes enviar tus sesiones al reloj."],
  cancelada: [false, "Has cancelado la autorización en COROS."],
  error: [false, "No se pudo conectar con COROS. Vuelve a intentarlo."],
};

/**
 * Conexión oficial con COROS (OAuth de su servidor MCP) para enviar las sesiones del plan al
 * calendario y al reloj. Se entra en la web de COROS: aquí nunca se escribe la contraseña.
 */
export function CorosOfficial({ data }: { data: SourcesStatus }) {
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const shown = useRef(false);
  const [busy, setBusy] = useState(false);
  const c = data.coros_official;
  const sync = useSyncCorosOfficial();

  // Vuelta de COROS: ?coros=ok|cancelada|error
  useEffect(() => {
    const result = params.get("coros");
    if (!result || shown.current || !RESULT[result]) return;
    shown.current = true;
    const [ok, text] = RESULT[result];
    if (ok) toast.success(text);
    else toast.error(text);
    queryClient.invalidateQueries({ queryKey: ["sources"] });
    queryClient.invalidateQueries({ queryKey: ["workout-settings"] });
    window.history.replaceState(null, "", window.location.pathname);
  }, [params, queryClient]);

  const connect = async () => {
    setBusy(true);
    try {
      const { url } = await apiFetch<{ url: string }>(
        "/api/v1/sources/coros-official/connect",
        {
          method: "POST",
          body: JSON.stringify({ origin: window.location.origin }),
        },
      );
      window.location.assign(url);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo conectar.",
      );
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await apiFetch<void>("/api/v1/sources/coros-official", {
        method: "DELETE",
      });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["workout-settings"] });
      toast.success("Conexión oficial con COROS quitada.");
    } catch {
      toast.error("No se pudo desconectar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section icon={CalendarCheck} title="COROS (conexión oficial)">
      <p className="text-xs text-muted-foreground">
        Una sola conexión para todo: trae tus actividades (con ruta, pulso y
        vueltas) y tu FC en reposo, HRV y sueño, y envía las sesiones del plan
        al calendario y al reloj. Entras en la web de COROS y autorizas la app:
        aquí no se escribe ni se guarda tu contraseña, y puedes revocarlo cuando
        quieras.
      </p>
      {c ? (
        <>
          <p className="text-sm">
            {c.status === "ok" ? "Conectado" : "Hay que volver a conectar"} ·
            desde {formatDateTime(c.connected_at)}
            {c.last_sync_at
              ? ` · actividades traídas ${formatDateTime(c.last_sync_at)}`
              : ""}
          </p>
          {c.last_error && (
            <p className="text-sm text-destructive">{c.last_error}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {c.status === "ok" && (
              <Button
                variant="outline"
                className="min-h-11 md:min-h-9"
                disabled={sync.isPending}
                onClick={() =>
                  sync.mutate(undefined, {
                    onSuccess: () =>
                      toast.success(
                        "Trayendo tus actividades de COROS: aparecerán en unos minutos.",
                      ),
                    onError: () => toast.error("No se pudo sincronizar."),
                  })
                }
              >
                <RefreshCw aria-hidden /> Traer actividades ahora
              </Button>
            )}
            {c.status !== "ok" && (
              <Button
                className="min-h-11 md:min-h-9"
                disabled={busy}
                onClick={connect}
              >
                <Link2 aria-hidden /> Volver a conectar
              </Button>
            )}
            <Button
              variant="ghost"
              className="min-h-11 text-destructive md:min-h-9"
              disabled={busy}
              onClick={disconnect}
            >
              <Trash2 aria-hidden /> Desconectar
            </Button>
          </div>
        </>
      ) : (
        <Button
          className="min-h-11 md:min-h-9 md:w-fit"
          disabled={busy}
          onClick={connect}
        >
          {busy ? <Loader2 className="animate-spin" /> : <Link2 aria-hidden />}
          Conectar con COROS
        </Button>
      )}
      <p className="text-xs text-muted-foreground">
        COROS no deja borrar entrenos desde fuera: si borras una sesión o la
        cambias de día, quita la antigua en la app de COROS.
      </p>
    </Section>
  );
}
