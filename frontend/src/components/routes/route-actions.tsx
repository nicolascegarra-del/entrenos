"use client";

import { CalendarPlus, Download, Loader2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { AskCoach } from "@/components/activity/ask-ai";
import { Button } from "@/components/ui/button";
import { useDeleteRoute, usePlans, useSetSessionRoute } from "@/hooks/use-api";
import { ApiError, authFetch, parseError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { addDays, toIsoDay } from "@/lib/plan";
import type { PlannedRouteDetail } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar.";

/** GPX para importar la ruta en Garmin Connect, COROS, Suunto, Polar… */
async function downloadGpx(route: PlannedRouteDetail) {
  const res = await authFetch(`/api/v1/planned-routes/${route.id}/gpx`);
  if (!res.ok) throw await parseError(res);
  const name =
    /filename="([^"]+)"/.exec(
      res.headers.get("content-disposition") ?? "",
    )?.[1] ?? "ruta.gpx";
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Exportar, usar en el plan, preguntar al entrenador y borrar una ruta guardada. */
export function RouteActions({ route }: { route: PlannedRouteDetail }) {
  const router = useRouter();
  const today = new Date();
  const from = toIsoDay(today);
  const { data: upcoming } = usePlans(from, toIsoDay(addDays(today, 60)));
  const setRoute = useSetSessionRoute();
  const remove = useDeleteRoute();
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const free = (upcoming ?? []).filter(
    (s) => !s.activity_id && s.planned_route_id !== route.id,
  );
  const question =
    `Tengo la ruta «${route.name}» (id ${route.id}): ${(route.distance_m / 1000).toFixed(1)} km con ` +
    `+${route.ascent_m} m de desnivel. ¿A qué ritmo la hago, cuánto tardaré y qué llevo (agua, geles)?`;

  return (
    <div className="space-y-4 rounded-lg border bg-card p-3 md:p-4">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await downloadGpx(route);
            } catch (err) {
              toast.error(errorText(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <Download aria-hidden />
          )}
          Exportar GPX para el reloj
        </Button>
        <AskCoach question={question} />
      </div>
      <p className="text-xs text-muted-foreground">
        Importa el GPX en Garmin Connect (Entrenamiento → Recorridos →
        Importar), en la app de COROS (Perfil → Rutas → Importar) o en la de tu
        marca, y sincroniza el reloj.
      </p>

      <div className="space-y-2 border-t pt-3">
        <p className="text-sm font-medium">Usar en el plan</p>
        {route.sessions.length > 0 && (
          <ul className="space-y-1 text-sm">
            {route.sessions.map((s) => (
              <li key={s.id}>
                <Link
                  href={`/plan/${s.id}`}
                  className="text-klyp-accent hover:underline"
                >
                  {formatDate(`${s.day}T12:00:00`)} · {s.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Sesión del plan"
            className="h-11 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm md:h-9"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          >
            <option value="">Elige una sesión de los próximos días…</option>
            {free.map((s) => (
              <option key={s.id} value={s.id}>
                {formatDate(`${s.day}T12:00:00`)} · {s.title}
              </option>
            ))}
          </select>
          <Button
            className="min-h-11 md:min-h-9"
            disabled={!sessionId || setRoute.isPending}
            onClick={() =>
              setRoute.mutate(
                { planId: Number(sessionId), routeId: route.id },
                {
                  onSuccess: () => {
                    toast.success("Ruta añadida a la sesión.");
                    setSessionId("");
                  },
                  onError: (err) => toast.error(errorText(err)),
                },
              )
            }
          >
            <CalendarPlus aria-hidden /> Añadir
          </Button>
        </div>
        <Button
          asChild
          variant="ghost"
          className="min-h-11 px-0 text-klyp-accent md:min-h-8"
        >
          <Link href={`/plan/nueva?dia=${from}&ruta=${route.id}`}>
            O crea una sesión nueva con esta ruta
          </Link>
        </Button>
      </div>

      <div className="border-t pt-3">
        <Button
          variant="ghost"
          className="min-h-11 text-destructive md:min-h-9"
          disabled={remove.isPending}
          onClick={() => {
            if (!window.confirm(`¿Borrar la ruta «${route.name}»?`)) return;
            remove.mutate(route.id, {
              onSuccess: () => {
                toast.success("Ruta borrada.");
                router.replace("/plan/rutas");
              },
              onError: (err) => toast.error(errorText(err)),
            });
          }}
        >
          <Trash2 aria-hidden /> Borrar ruta
        </Button>
      </div>
    </div>
  );
}
