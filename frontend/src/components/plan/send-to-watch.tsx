"use client";

import {
  CircleAlert,
  CircleCheck,
  Download,
  Loader2,
  RefreshCw,
  Send,
  Watch,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  useCorosWorkout,
  useGarminWorkout,
  useSaveWorkoutSettings,
  useSendUpcoming,
  useWorkoutSettings,
} from "@/hooks/use-api";
import { ApiError, authFetch, parseError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { PlannedSession } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

/** Sesiones que se pueden enviar al reloj (de momento, carrera y bici). */
export const canSendToWatch = (sport: string) =>
  sport.includes("running") ||
  [
    "cycling",
    "road_biking",
    "mountain_biking",
    "indoor_cycling",
    "gravel_cycling",
    "virtual_ride",
  ].includes(sport);

/** Descarga la sesión como .FIT (con la sesión iniciada: no vale un enlace normal). */
async function downloadFit(planId: number) {
  const res = await authFetch(`/api/v1/plans/${planId}/workout.fit`);
  if (!res.ok) throw await parseError(res);
  const name =
    /filename="([^"]+)"/.exec(
      res.headers.get("content-disposition") ?? "",
    )?.[1] ?? "entreno.fit";
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Detalle de una sesión: enviarla a Garmin o COROS (o actualizarla) y descargarla en .FIT. */
export function SendToWatchCard({ plan }: { plan: PlannedSession }) {
  const { data: settings } = useWorkoutSettings();
  const garmin = useGarminWorkout(plan.id);
  const [downloading, setDownloading] = useState(false);
  if (!canSendToWatch(plan.sport)) return null;
  const sent = plan.garmin_status === "sent";
  const send = () =>
    garmin.mutate(false, {
      onSuccess: (r) =>
        r.garmin_status === "sent"
          ? toast.success(
              "Enviada a Garmin: llegará al reloj cuando sincronice.",
            )
          : toast.error(r.garmin_error || "Garmin no aceptó el entreno."),
      onError: (err) => toast.error(errorText(err)),
    });
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Watch className="size-5 text-klyp-accent" aria-hidden /> En tu reloj
        </CardTitle>
        <CardDescription>
          Con los pasos, las repeticiones y los objetivos de ritmo, FC o
          potencia, para seguirla en el reloj.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {sent && !plan.garmin_outdated && (
          <p className="flex items-start gap-2 text-sm">
            <CircleCheck
              className="mt-0.5 size-4 shrink-0 text-emerald-600"
              aria-hidden
            />
            En tu calendario de Garmin
            {plan.garmin_sent_at
              ? ` desde ${formatDateTime(plan.garmin_sent_at)}`
              : ""}
            . El reloj la recibe al sincronizar.
          </p>
        )}
        {sent && plan.garmin_outdated && (
          <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            Has cambiado la sesión después de enviarla: actualízala en Garmin.
          </p>
        )}
        {plan.garmin_status === "error" && (
          <p className="flex items-start gap-2 text-sm text-destructive">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {plan.garmin_error || "No se pudo enviar."}
          </p>
        )}
        {settings?.coros_connected && <CorosRow plan={plan} />}
        <div className="flex flex-wrap gap-2">
          {settings?.garmin_connected ? (
            <>
              <Button
                className="min-h-11 md:min-h-9"
                variant={sent && !plan.garmin_outdated ? "outline" : "default"}
                disabled={garmin.isPending}
                onClick={send}
              >
                {garmin.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : sent ? (
                  <RefreshCw aria-hidden />
                ) : (
                  <Send aria-hidden />
                )}
                {sent ? "Actualizar en Garmin" : "Enviar a Garmin"}
              </Button>
              {sent && (
                <Button
                  variant="ghost"
                  className="min-h-11 text-muted-foreground md:min-h-9"
                  disabled={garmin.isPending}
                  onClick={() =>
                    garmin.mutate(true, {
                      onSuccess: () => toast.success("Quitada de Garmin."),
                      onError: (err) => toast.error(errorText(err)),
                    })
                  }
                >
                  <X aria-hidden /> Quitar de Garmin
                </Button>
              )}
            </>
          ) : (
            settings &&
            !settings.coros_connected && (
              <p className="text-sm text-muted-foreground">
                Para enviarla a tu Garmin o COROS,{" "}
                <Link
                  href="/ajustes/conexiones"
                  className="text-klyp-accent underline"
                >
                  conecta tu cuenta
                </Link>
                .
              </p>
            )
          )}
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            disabled={downloading}
            onClick={async () => {
              setDownloading(true);
              try {
                await downloadFit(plan.id);
              } catch (err) {
                toast.error(errorText(err));
              } finally {
                setDownloading(false);
              }
            }}
          >
            {downloading ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Download aria-hidden />
            )}
            Descargar .FIT
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          El .FIT sirve para un Garmin por USB (cópialo en la carpeta
          «NewFiles»), Wahoo, Hammerhead y apps que importen entrenos FIT. COROS
          y Suunto no lo importan, y Apple Watch no permite recibir entrenos
          desde una web.
        </p>
        {settings?.auto && (
          <p className="text-xs text-muted-foreground">
            Tienes activado el envío automático de los próximos {settings.days}{" "}
            días.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Envío a COROS de una sesión: estado y botón (COROS no deja borrar ni mover desde fuera). */
function CorosRow({ plan }: { plan: PlannedSession }) {
  const coros = useCorosWorkout(plan.id);
  const sent = plan.coros_status === "sent";
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <p className="text-sm font-medium">COROS</p>
      {sent && !plan.coros_outdated && (
        <p className="flex items-start gap-2 text-sm">
          <CircleCheck
            className="mt-0.5 size-4 shrink-0 text-emerald-600"
            aria-hidden
          />
          En tu calendario de COROS
          {plan.coros_sent_at
            ? ` desde ${formatDateTime(plan.coros_sent_at)}`
            : ""}
          . El reloj la recibe al sincronizar con la app de COROS.
        </p>
      )}
      {sent && plan.coros_outdated && (
        <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          Has cambiado la sesión después de enviarla: actualízala en COROS.
        </p>
      )}
      {plan.coros_error && (
        <p
          className={
            plan.coros_status === "error"
              ? "flex items-start gap-2 text-sm text-destructive"
              : "flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400"
          }
        >
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {plan.coros_error}
        </p>
      )}
      <Button
        className="min-h-11 md:min-h-9"
        variant={sent && !plan.coros_outdated ? "outline" : "default"}
        disabled={coros.isPending}
        onClick={() =>
          coros.mutate(undefined, {
            onSuccess: (r) =>
              r.coros_status === "sent"
                ? toast.success("En tu calendario de COROS.")
                : toast.error(r.coros_error || "COROS no aceptó el entreno."),
            onError: (err) => toast.error(errorText(err)),
          })
        }
      >
        {coros.isPending ? (
          <Loader2 className="animate-spin" />
        ) : sent ? (
          <RefreshCw aria-hidden />
        ) : (
          <Send aria-hidden />
        )}
        {sent ? "Actualizar en COROS" : "Enviar a COROS"}
      </Button>
    </div>
  );
}

/** Botón del calendario: enviar a tus relojes (Garmin y COROS) las sesiones de hoy y los próximos 6 días. */
export function SendUpcomingButton() {
  const { data: settings } = useWorkoutSettings();
  const send = useSendUpcoming();
  if (!settings?.garmin_connected && !settings?.coros_connected) return null;
  return (
    <Button
      data-tour="send-watch"
      variant="outline"
      className="min-h-11 md:min-h-9"
      disabled={send.isPending}
      onClick={() =>
        send.mutate(undefined, {
          onSuccess: (r) => {
            const total = r.sent + r.unchanged;
            if (r.error)
              toast.error(
                `${r.error} no se pudieron enviar: abre la sesión para ver el motivo.`,
              );
            else if (!total)
              toast(
                "No hay sesiones de carrera o bici en los próximos 7 días.",
              );
            else
              toast.success(
                r.sent
                  ? `${r.sent} enviadas al reloj${r.unchanged ? ` (${r.unchanged} ya estaban)` : ""}.`
                  : "Ya estaban todas en el reloj.",
              );
          },
          onError: (err) => toast.error(errorText(err)),
        })
      }
    >
      {send.isPending ? (
        <Loader2 className="animate-spin" />
      ) : (
        <Watch aria-hidden />
      )}
      <span className="md:hidden">Al reloj</span>
      <span className="hidden md:inline">Enviar 7 días al reloj</span>
    </Button>
  );
}

/** Ajustes → Conexiones (Garmin o COROS): envío automático de las sesiones a los relojes conectados. */
export function GarminWorkoutsCard() {
  const { data } = useWorkoutSettings();
  const save = useSaveWorkoutSettings();
  if (!data?.garmin_connected && !data?.coros_connected) return null;
  const where = [
    data.garmin_connected && "Garmin Connect",
    data.coros_connected && "COROS",
  ]
    .filter(Boolean)
    .join(" y ");
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Send className="size-5 text-klyp-accent" aria-hidden /> Enviar tus
          sesiones al reloj
        </CardTitle>
        <CardDescription>
          Tus sesiones de carrera y bici del plan aparecen en el calendario de{" "}
          {where} y en tu reloj, con sus pasos y objetivos.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <label className="flex min-h-11 cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            className="mt-0.5 size-5"
            checked={data.auto}
            disabled={save.isPending}
            onChange={(e) =>
              save.mutate(e.target.checked, {
                onSuccess: (r) =>
                  toast.success(
                    r.auto
                      ? "Activado: enviando las sesiones de los próximos 7 días."
                      : "Envío automático desactivado.",
                  ),
                onError: (err) => toast.error(errorText(err)),
              })
            }
          />
          <span className="text-sm">
            <span className="block font-medium">
              Enviar automáticamente los próximos {data.days} días
            </span>
            <span className="block text-muted-foreground">
              Cada 6 horas y cada vez que guardas una sesión. Si la cambias, se
              actualiza; si la borras, en Garmin se quita sola y en COROS hay
              que quitarla desde su app.
            </span>
          </span>
        </label>
      </CardContent>
    </Card>
  );
}
