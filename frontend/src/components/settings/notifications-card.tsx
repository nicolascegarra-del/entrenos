"use client";

import { Bell, BellOff, Loader2, Send, Smartphone, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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
  useNotifications,
  useRemovePushDevice,
  useSaveNotificationPrefs,
  useSubscribePush,
  useTestPush,
  useUnsubscribePush,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  browserPushSupport,
  currentSubscription,
  deviceLabel,
  registerServiceWorker,
  urlBase64ToUint8Array,
  type PushSupport,
} from "@/lib/push";
import type { NotificationPrefs } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const KINDS: { key: keyof NotificationPrefs; label: string; help: string }[] = [
  {
    key: "daily_session",
    label: "Sesión del día",
    help: "«Hoy toca…» a la hora que elijas, si tienes algo planificado.",
  },
  {
    key: "overload",
    label: "Riesgo de lesión",
    help: "Cuando tu carga entra en «Atención» (como mucho uno por semana).",
  },
  {
    key: "plan_changes",
    label: "Cambios del plan",
    help: "El ajuste semanal de tu plan automático y por qué.",
  },
  {
    key: "activity_reviews",
    label: "Análisis de tus entrenos",
    help: "Cuando la IA termina el análisis de un entreno recién sincronizado.",
  },
  {
    key: "tests",
    label: "Resultados de tus tests",
    help: "Cuando un test planificado se analiza al sincronizarlo, para que lo revises.",
  },
  {
    key: "weekly_review",
    label: "Revisión semanal",
    help: "El domingo por la tarde, tu entrenador IA te pregunta qué tal la semana.",
  },
  {
    key: "achievements",
    label: "Récords y logros",
    help: "Nuevas mejores marcas y retos conseguidos.",
  },
  {
    key: "sync_error",
    label: "Problemas con Garmin",
    help: "Si la sincronización falla o la conexión caduca.",
  },
];

const SUPPORT_TEXT: Record<Exclude<PushSupport, "ok">, string> = {
  "ios-install":
    "En iPhone y iPad las notificaciones solo funcionan con la app instalada: pulsa Compartir → «Añadir a pantalla de inicio» y ábrela desde allí.",
  unsupported: "Este navegador no admite notificaciones push.",
  insecure:
    "Las notificaciones necesitan una conexión segura (HTTPS). Abre la app desde su dirección https.",
};

/** Ajustes → Notificaciones: activar en este dispositivo, qué avisos y prueba. */
export function NotificationsCard() {
  const { data, isPending } = useNotifications();
  const savePrefs = useSaveNotificationPrefs();
  const subscribe = useSubscribePush();
  const unsubscribe = useUnsubscribePush();
  const removeDevice = useRemovePushDevice();
  const test = useTestPush();
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [permission, setPermission] = useState<NotificationPermission>();
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Solo en el navegador: compatibilidad, permiso y si este dispositivo ya está suscrito.
  useEffect(() => {
    const s = browserPushSupport();
    setSupport(s);
    if (s !== "ok") return;
    setPermission(Notification.permission);
    currentSubscription()
      .then((sub) => setEndpoint(sub?.endpoint ?? null))
      .catch(() => setEndpoint(null));
  }, []);

  const enable = async () => {
    if (!data) return;
    setBusy(true);
    try {
      const result = await Notification.requestPermission();
      setPermission(result);
      if (result !== "granted") {
        toast.error(
          "Has bloqueado las notificaciones. Actívalas en los ajustes del navegador para esta web.",
        );
        return;
      }
      const reg = await registerServiceWorker();
      await navigator.serviceWorker.ready;
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(data.public_key),
        }));
      const json = sub.toJSON();
      await subscribe.mutateAsync({
        endpoint: sub.endpoint,
        keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
        user_agent: navigator.userAgent,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      setEndpoint(sub.endpoint);
      toast.success("Notificaciones activadas en este dispositivo.");
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      const sub = await currentSubscription();
      if (sub) {
        await unsubscribe.mutateAsync({ endpoint: sub.endpoint });
        await sub.unsubscribe();
      }
      setEndpoint(null);
      toast.success("Este dispositivo ya no recibirá avisos.");
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const setPref = (patch: Partial<NotificationPrefs>) => {
    if (!data) return;
    savePrefs.mutate(
      { ...data.prefs, ...patch },
      { onError: (err) => toast.error(errorText(err)) },
    );
  };

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Bell className="size-5 text-klyp-accent" aria-hidden />
          Notificaciones
        </CardTitle>
        <CardDescription>
          Avisos en el móvil o el ordenador, aunque no tengas la app abierta.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending || support === null ? (
          <Skeleton className="h-40" />
        ) : !data ? (
          <p className="text-sm text-muted-foreground">
            No se pudo cargar la configuración.
          </p>
        ) : (
          <>
            {support !== "ok" ? (
              <p className="rounded-lg bg-muted/60 p-3 text-sm">
                {SUPPORT_TEXT[support]}
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                {endpoint ? (
                  <>
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      <Smartphone className="size-4" aria-hidden />
                      Activadas en este dispositivo
                    </p>
                    <Button
                      variant="outline"
                      className="min-h-11 md:min-h-9"
                      disabled={test.isPending}
                      onClick={() =>
                        test.mutate(undefined, {
                          onSuccess: (r) =>
                            r.sent
                              ? toast.success(
                                  "Enviada: debería llegarte en unos segundos.",
                                )
                              : toast.error(
                                  "No se pudo entregar. Desactiva y vuelve a activar las notificaciones.",
                                ),
                          onError: (err) => toast.error(errorText(err)),
                        })
                      }
                    >
                      {test.isPending ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Send aria-hidden />
                      )}
                      Enviar una de prueba
                    </Button>
                    <Button
                      variant="ghost"
                      className="min-h-11 md:min-h-9"
                      disabled={busy}
                      onClick={disable}
                    >
                      <BellOff aria-hidden /> Desactivar aquí
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      className="min-h-11 md:min-h-9"
                      disabled={busy}
                      onClick={enable}
                    >
                      {busy ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Bell aria-hidden />
                      )}
                      Activar en este dispositivo
                    </Button>
                    {permission === "denied" && (
                      <p className="text-xs text-destructive">
                        Las notificaciones están bloqueadas para esta web en el
                        navegador: permítelas desde el candado de la barra de
                        direcciones.
                      </p>
                    )}
                  </>
                )}
              </div>
            )}

            <fieldset className="space-y-1" disabled={savePrefs.isPending}>
              <legend className="mb-1 text-sm font-medium">
                Qué quieres que te avisemos
              </legend>
              {KINDS.map((k) => (
                <label
                  key={k.key}
                  className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md p-2 hover:bg-muted/60"
                >
                  <input
                    type="checkbox"
                    className="mt-1 size-4 shrink-0"
                    checked={Boolean(data.prefs[k.key])}
                    onChange={(e) => setPref({ [k.key]: e.target.checked })}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{k.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {k.help}
                    </span>
                  </span>
                </label>
              ))}
              <div className="flex flex-wrap items-center gap-2 pl-9">
                <label htmlFor="daily-hour" className="text-sm">
                  Hora del aviso diario
                </label>
                <select
                  id="daily-hour"
                  className="h-11 rounded-md border border-input bg-background px-2 text-sm md:h-8"
                  value={data.prefs.daily_hour}
                  disabled={!data.prefs.daily_session}
                  onChange={(e) =>
                    setPref({ daily_hour: Number(e.target.value) })
                  }
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, "0")}:00
                    </option>
                  ))}
                </select>
                <span className="text-xs text-muted-foreground">
                  ({data.prefs.timezone})
                </span>
              </div>
            </fieldset>

            {data.devices.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm font-medium">Dispositivos con avisos</p>
                <ul className="space-y-1">
                  {data.devices.map((d) => (
                    <li
                      key={d.id}
                      className="flex items-center gap-2 rounded-md bg-muted/60 px-2 text-sm"
                    >
                      <Smartphone
                        className="size-4 shrink-0 text-muted-foreground"
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {deviceLabel(d.user_agent)}
                        <span className="text-xs text-muted-foreground">
                          {" "}
                          · desde {formatDateTime(d.created_at)}
                        </span>
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-11 shrink-0 md:size-8"
                        aria-label={`Quitar ${deviceLabel(d.user_agent)}`}
                        disabled={removeDevice.isPending}
                        onClick={() =>
                          removeDevice.mutate(d.id, {
                            onError: (err) => toast.error(errorText(err)),
                          })
                        }
                      >
                        <X aria-hidden />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {data.recent.length > 0 && (
              <details className="text-sm">
                <summary className="min-h-11 cursor-pointer content-center font-medium">
                  Últimos avisos enviados
                </summary>
                <ul className="mt-1 space-y-1 text-muted-foreground">
                  {data.recent.map((n, i) => (
                    <li key={i}>
                      {formatDateTime(n.sent_at)} · {n.title}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
