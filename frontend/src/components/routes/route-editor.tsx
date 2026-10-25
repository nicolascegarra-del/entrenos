"use client";

import {
  Layers,
  Loader2,
  LocateFixed,
  Repeat,
  RotateCcw,
  Save,
  Search,
  Trash2,
  Undo2,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ElevationProfile } from "@/components/routes/elevation-profile";
import type { MapLayer } from "@/components/routes/route-editor-map";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { geocodePlace, usePlanRoute, useSaveRoute } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import {
  addPoint,
  closeLoop,
  type LatLon,
  MAX_ROUTE_POINTS,
  movePoint,
  outAndBack,
  pointAtDistance,
  removePoint,
  ROUTE_MODES,
  type RouteMode,
} from "@/lib/route-edit";
import { cn } from "@/lib/utils";
import type { GeoResult, PlannedRouteDetail, RoutePlan } from "@/types/api";

const RouteEditorMap = dynamic(
  () => import("@/components/routes/route-editor-map"),
  {
    ssr: false,
    loading: () => <Skeleton className="size-full" />,
  },
);

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo calcular la ruta.";

/** Barras de reparto (superficie o tipo de vía). */
export function ShareBars({
  title,
  items,
}: {
  title: string;
  items: RoutePlan["surfaces"];
}) {
  if (!items.length) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      {items.map((s) => (
        <div key={s.tipo} className="text-xs">
          <div className="flex justify-between gap-2">
            <span>{s.tipo}</span>
            <span className="tabular-nums text-muted-foreground">
              {(s.distancia_m / 1000).toLocaleString("es-ES", {
                maximumFractionDigits: 1,
              })}{" "}
              km · {s.pct} %
            </span>
          </div>
          <div className="mt-0.5 h-1.5 rounded-full bg-muted">
            <div
              className="h-1.5 rounded-full bg-[var(--chart-1)]"
              style={{ width: `${s.pct}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Km, desnivel, tiempo estimado y altitudes de la ruta. */
export function RouteStatsGrid({
  plan,
}: {
  plan: Pick<RoutePlan, "distance_m" | "ascent_m" | "descent_m"> & {
    estimated_s: number | null;
  };
}) {
  const items = [
    [
      "Distancia",
      `${(plan.distance_m / 1000).toLocaleString("es-ES", { maximumFractionDigits: 2 })} km`,
    ],
    ["Desnivel +", `${plan.ascent_m} m`],
    ["Desnivel −", `${plan.descent_m} m`],
    ["Tiempo est.", plan.estimated_s ? formatDuration(plan.estimated_s) : "—"],
  ];
  return (
    <dl className="grid grid-cols-4 gap-2 lg:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="rounded-md bg-muted/60 p-2">
          <dt className="text-[11px] text-muted-foreground">{k}</dt>
          <dd className="font-heading text-sm font-semibold tabular-nums md:text-base">
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Editor de rutas: toca el mapa para marcar inicio, puntos de paso y fin; la ruta se calcula por asfalto,
 * senderos o en bici, con km, desnivel, perfil y tiempo estimado. Sirve para crear y para editar.
 */
export function RouteEditor({ initial }: { initial?: PlannedRouteDetail }) {
  const router = useRouter();
  const plan = usePlanRoute();
  const save = useSaveRoute();
  const [mode, setMode] = useState<RouteMode>(
    (initial?.mode as RouteMode) ?? "asfalto",
  );
  const [history, setHistory] = useState<LatLon[][]>([
    (initial?.waypoints as LatLon[] | undefined) ?? [],
  ]);
  const points = history[history.length - 1];
  const [result, setResult] = useState<RoutePlan | null>(
    initial
      ? {
          mode: initial.mode,
          geometry: initial.geometry,
          distance_m: initial.distance_m,
          ascent_m: initial.ascent_m,
          descent_m: initial.descent_m,
          profile: initial.profile,
          surfaces: initial.surfaces,
          waytypes: initial.waytypes,
          max_altitude_m: null,
          min_altitude_m: null,
          estimated_s: initial.estimated_s ?? 0,
          estimate_basis: "",
        }
      : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState(initial?.name ?? "");
  const [layer, setLayer] = useState<MapLayer>(
    initial && (initial.mode === "trail" || initial.mode === "mtb")
      ? "topo"
      : "mapa",
  );
  const [center, setCenter] = useState<LatLon | null>(null);
  const [fitKey, setFitKey] = useState(initial ? 1 : 0);
  const [hover, setHover] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<GeoResult[]>([]);
  const dirty = useRef(false);

  const push = (next: LatLon[]) => {
    if (next === points) return;
    dirty.current = true;
    setHistory((h) => [...h.slice(-40), next]);
  };

  // Recalcula 400 ms después del último cambio (puntos o modo).
  useEffect(() => {
    if (!dirty.current) return;
    if (points.length < 2) {
      setResult(null);
      setError(null);
      return;
    }
    const t = setTimeout(() => {
      plan.mutate(
        { mode, points: points.map(([lat, lon]) => ({ lat, lon })) },
        {
          onSuccess: (r) => {
            setResult(r);
            setError(null);
          },
          onError: (e) => setError(errorText(e)),
        },
      );
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, mode]);

  const hoverPoint = useMemo(
    () =>
      hover != null && result ? pointAtDistance(result.geometry, hover) : null,
    [hover, result],
  );

  const changeMode = (m: RouteMode) => {
    dirty.current = true;
    setMode(m);
    if (m === "trail" || m === "mtb") setLayer("topo");
  };

  const locate = () => {
    if (!navigator.geolocation)
      return toast.error("Tu navegador no da la ubicación.");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCenter([pos.coords.latitude, pos.coords.longitude]);
        setFitKey((k) => k + 1);
      },
      () => toast.error("No se pudo obtener tu ubicación (revisa el permiso)."),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length < 2) return;
    try {
      setPlaces(await geocodePlace(query.trim()));
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  const onSave = () => {
    if (!name.trim()) return toast.error("Ponle un nombre a la ruta.");
    save.mutate(
      {
        id: initial?.id,
        name: name.trim(),
        mode,
        points: points.map(([lat, lon]) => ({ lat, lon })),
      },
      {
        onSuccess: (route) => {
          toast.success("Ruta guardada.");
          dirty.current = false;
          if (!initial) router.replace(`/plan/rutas/${route.id}`);
        },
        onError: (err) => toast.error(errorText(err)),
      },
    );
  };

  const canSave = points.length >= 2 && !!result && !error && !plan.isPending;
  return (
    <div className="space-y-3 lg:grid lg:grid-cols-[1fr_22rem] lg:gap-4 lg:space-y-0">
      <div className="space-y-2">
        {/* Modo y buscador */}
        <div className="flex flex-wrap items-center gap-2">
          <div
            role="radiogroup"
            aria-label="Tipo de ruta"
            className="flex gap-1 overflow-x-auto rounded-lg bg-muted p-1"
          >
            {ROUTE_MODES.map((m) => (
              <button
                key={m.key}
                type="button"
                role="radio"
                aria-checked={mode === m.key}
                title={m.hint}
                onClick={() => changeMode(m.key)}
                className={cn(
                  "min-h-11 shrink-0 rounded-md px-3 text-sm font-medium md:min-h-8",
                  mode === m.key
                    ? "bg-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          <form onSubmit={search} className="relative min-w-48 flex-1">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar un lugar"
              aria-label="Buscar un lugar"
              className="h-11 pl-9 md:h-9"
            />
            {places.length > 0 && (
              <ul className="absolute inset-x-0 top-full z-[500] mt-1 overflow-hidden rounded-md border bg-popover shadow-md">
                {places.map((p) => (
                  <li key={`${p.lat}-${p.lon}`}>
                    <button
                      type="button"
                      className="min-h-11 w-full px-3 text-left text-sm hover:bg-muted"
                      onClick={() => {
                        setCenter([p.lat, p.lon]);
                        setFitKey((k) => k + 1);
                        setPlaces([]);
                        setQuery(p.label);
                      }}
                    >
                      {p.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
        </div>

        {/* Mapa */}
        <div className="relative h-[58dvh] min-h-80 overflow-hidden rounded-lg border lg:h-[calc(100dvh-12rem)]">
          <RouteEditorMap
            points={points}
            geometry={result?.geometry ?? []}
            hover={hoverPoint}
            layer={layer}
            center={center}
            fitKey={fitKey}
            loading={plan.isPending}
            onAdd={(p) => {
              if (points.length >= MAX_ROUTE_POINTS)
                return toast.error(
                  `Como mucho ${MAX_ROUTE_POINTS} puntos por ruta.`,
                );
              push(addPoint(points, p));
            }}
            onMove={(i, p) => push(movePoint(points, i, p))}
            onRemove={(i) => push(removePoint(points, i))}
          />
          {points.length === 0 && (
            <p className="pointer-events-none absolute top-3 right-3 left-14 z-[400] rounded-md bg-background/95 p-2 text-center text-sm shadow-sm">
              Toca el mapa para marcar el inicio, luego los puntos de paso y el
              final.
            </p>
          )}
          {plan.isPending && (
            <span className="absolute top-3 right-3 z-[400] inline-flex items-center gap-1.5 rounded-md bg-background/95 px-2 py-1 text-xs shadow-sm">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />{" "}
              Calculando…
            </span>
          )}
          <div className="absolute right-3 bottom-6 z-[400] flex flex-col gap-2">
            <Button
              size="icon"
              variant="secondary"
              className="size-11 shadow-md"
              aria-label="Ir a mi ubicación"
              onClick={locate}
            >
              <LocateFixed aria-hidden />
            </Button>
            <Button
              size="icon"
              variant="secondary"
              className="size-11 shadow-md"
              aria-label={
                layer === "topo" ? "Ver mapa normal" : "Ver mapa topográfico"
              }
              onClick={() => setLayer((l) => (l === "topo" ? "mapa" : "topo"))}
            >
              <Layers aria-hidden />
            </Button>
          </div>
        </div>

        {/* Acciones (bajo el mapa, a mano del pulgar) */}
        <div className="grid grid-cols-4 gap-1.5">
          <Button
            variant="outline"
            className="min-h-11 flex-col gap-0.5 px-1 text-xs md:flex-row md:gap-2 md:text-sm"
            disabled={history.length < 2}
            onClick={() => {
              dirty.current = true;
              setHistory((h) => h.slice(0, -1));
            }}
          >
            <Undo2 aria-hidden /> Deshacer
          </Button>
          <Button
            variant="outline"
            className="min-h-11 flex-col gap-0.5 px-1 text-xs md:flex-row md:gap-2 md:text-sm"
            disabled={points.length < 2}
            onClick={() => {
              const next = outAndBack(points);
              if (!next)
                return toast.error(
                  `Demasiados puntos para ida y vuelta (máx. ${MAX_ROUTE_POINTS}).`,
                );
              push(next);
            }}
          >
            <Repeat aria-hidden /> Ida y vuelta
          </Button>
          <Button
            variant="outline"
            className="min-h-11 flex-col gap-0.5 px-1 text-xs md:flex-row md:gap-2 md:text-sm"
            disabled={points.length < 2}
            onClick={() => push(closeLoop(points))}
          >
            <RotateCcw aria-hidden /> Circular
          </Button>
          <Button
            variant="outline"
            className="min-h-11 flex-col gap-0.5 px-1 text-xs text-destructive md:flex-row md:gap-2 md:text-sm"
            disabled={!points.length}
            onClick={() => {
              if (window.confirm("¿Borrar todos los puntos?")) push([]);
            }}
          >
            <Trash2 aria-hidden /> Borrar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Arrastra un punto para moverlo; mantenlo pulsado (o clic derecho) para
          quitarlo.
        </p>
      </div>

      {/* Panel: datos, perfil y guardar */}
      <aside className="space-y-4 rounded-lg border bg-card p-3 md:p-4 lg:max-h-[calc(100dvh-9rem)] lg:overflow-y-auto">
        {error && (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
          >
            {error}
          </p>
        )}
        {result ? (
          <>
            <RouteStatsGrid plan={result} />
            {result.estimate_basis && (
              <p className="text-xs text-muted-foreground">
                Tiempo estimado con {result.estimate_basis}, corregido por la
                pendiente.
              </p>
            )}
            <ElevationProfile profile={result.profile} onHover={setHover} />
            <ShareBars title="Superficie" items={result.surfaces} />
            <ShareBars title="Tipo de vía" items={result.waytypes} />
          </>
        ) : (
          !error && (
            <p className="text-sm text-muted-foreground">
              Marca al menos el inicio y el final para ver los kilómetros, el
              desnivel y el perfil.
            </p>
          )
        )}
        <div className="space-y-2 border-t pt-3">
          <label htmlFor="route-name" className="text-sm font-medium">
            Nombre de la ruta
          </label>
          <Input
            id="route-name"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ej. Vuelta al pantano"
            className="h-11 md:h-9"
          />
          <Button
            className="h-11 w-full"
            disabled={!canSave || save.isPending}
            onClick={onSave}
          >
            {save.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Save aria-hidden />
            )}
            {initial ? "Guardar cambios" : "Guardar ruta"}
          </Button>
        </div>
      </aside>
    </div>
  );
}
