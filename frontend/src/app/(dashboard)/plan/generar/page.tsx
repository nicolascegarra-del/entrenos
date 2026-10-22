"use client";

import { ArrowLeft, CalendarPlus, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreatePlan, useGoals, usePlanPreview } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate, formatDistance, formatNumber } from "@/lib/format";
import {
  isQuality,
  PHASE_HELP,
  planDaysValid,
  WEEKDAY_LONG,
  WEEKDAY_SHORT,
} from "@/lib/training-plan";
import { cn } from "@/lib/utils";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

function Generator() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: goals, isPending, isError, refetch } = useGoals();
  const upcoming = (goals ?? []).filter(
    (g) => g.days_left > 0 && g.result_time_s == null,
  );
  const [goalId, setGoalId] = useState<number | null>(
    Number(params.get("objetivo")) || null,
  );
  const [weekdays, setWeekdays] = useState<number[]>([1, 3, 6]);
  const [longDay, setLongDay] = useState(6);
  const preview = usePlanPreview();
  const create = useCreatePlan();

  useEffect(() => {
    if (goalId == null && upcoming.length) setGoalId(upcoming[0].id);
  }, [goalId, upcoming]);

  const valid = goalId != null && planDaysValid(weekdays, longDay);
  const body = goalId
    ? { goal_id: goalId, weekdays, long_run_weekday: longDay }
    : null;

  const toggle = (d: number) => {
    preview.reset();
    setWeekdays((w) =>
      w.includes(d) ? w.filter((x) => x !== d) : [...w, d].sort(),
    );
  };

  if (isPending) return <Skeleton className="h-64" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudieron cargar tus objetivos."
        onRetry={() => refetch()}
      />
    );
  if (!upcoming.length)
    return (
      <Card className="shadow-sm">
        <CardContent className="space-y-3 py-6 text-center">
          <p>Para generar un plan necesitas un objetivo de carrera futuro.</p>
          <Button asChild className="min-h-11">
            <Link href="/objetivos/nuevo">Crear un objetivo</Link>
          </Button>
        </CardContent>
      </Card>
    );

  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardContent className="space-y-4 pt-6">
          <div className="space-y-1.5">
            <Label htmlFor="goal">Objetivo</Label>
            <select
              id="goal"
              className={selectClass}
              value={goalId ?? ""}
              onChange={(e) => {
                preview.reset();
                setGoalId(Number(e.target.value));
              }}
            >
              {upcoming.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} · {formatDistance(g.distance_m)} ·{" "}
                  {formatDate(`${g.race_date}T12:00:00`)} (en {g.days_left}{" "}
                  días)
                </option>
              ))}
            </select>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">
              ¿Qué días puedes entrenar?
            </legend>
            <div className="flex flex-wrap gap-2">
              {WEEKDAY_SHORT.map((label, d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={weekdays.includes(d)}
                  aria-label={WEEKDAY_LONG[d]}
                  onClick={() => toggle(d)}
                  className={cn(
                    "size-11 rounded-full border text-sm font-medium",
                    weekdays.includes(d)
                      ? "border-klyp-accent bg-klyp-accent text-white"
                      : "hover:bg-muted",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {weekdays.length} días por semana. Lo ideal para empezar: 3–4.
            </p>
          </fieldset>

          <div className="space-y-1.5">
            <Label htmlFor="long-day">Día de la tirada larga</Label>
            <select
              id="long-day"
              className={selectClass}
              value={longDay}
              onChange={(e) => {
                preview.reset();
                setLongDay(Number(e.target.value));
              }}
            >
              {weekdays.map((d) => (
                <option key={d} value={d}>
                  {WEEKDAY_LONG[d]}
                </option>
              ))}
            </select>
            {!weekdays.includes(longDay) && (
              <p className="text-xs text-destructive">
                Elige un día de los que entrenas.
              </p>
            )}
          </div>

          <Button
            className="min-h-11 md:min-h-9"
            disabled={!valid || preview.isPending}
            onClick={() =>
              body &&
              preview.mutate(body, {
                onError: (err) => toast.error(errorText(err)),
              })
            }
          >
            {preview.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Sparkles aria-hidden />
            )}
            Ver el plan
          </Button>
        </CardContent>
      </Card>

      {preview.data && (
        <section className="space-y-3" aria-label="Vista previa del plan">
          <p className="text-sm text-muted-foreground">
            {preview.data.weeks.length} semanas. Empiezas desde{" "}
            {formatNumber(preview.data.start_km_week, 1)} km/semana (tu media de
            las últimas 4) y el volumen sube como mucho un 10 % por semana, con
            descarga cada 4. El plan se revisa solo cada lunes según lo que
            hagas.
          </p>
          <ol className="space-y-2">
            {preview.data.weeks.map((w) => (
              <li key={w.index} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Semana {w.index}</span>
                  <Badge variant="outline" title={PHASE_HELP[w.phase]}>
                    {w.phase_label}
                  </Badge>
                  {w.is_recovery && <Badge variant="secondary">Descarga</Badge>}
                  <span className="ml-auto text-sm tabular-nums">
                    {formatNumber(w.target_km, 1)} km
                  </span>
                </div>
                <ul className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
                  {w.sessions.map((s) => (
                    <li
                      key={s.day}
                      className={cn(
                        "rounded-md px-2 py-1",
                        isQuality(s.kind)
                          ? "bg-klyp-accent/15 font-medium"
                          : "bg-muted",
                      )}
                    >
                      {
                        WEEKDAY_SHORT[
                          (new Date(`${s.day}T12:00:00`).getDay() + 6) % 7
                        ]
                      }{" "}
                      · {s.title} · {formatNumber(s.km, 1)} km
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          <Button
            className="min-h-11 w-full md:w-auto"
            disabled={create.isPending}
            onClick={() =>
              body &&
              create.mutate(body, {
                onSuccess: () => {
                  toast.success(
                    "Plan creado: las sesiones ya están en tu calendario.",
                  );
                  router.push("/plan/entrenamiento");
                },
                onError: (err) => toast.error(errorText(err)),
              })
            }
          >
            {create.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <CalendarPlus aria-hidden />
            )}
            Crear el plan y añadirlo al calendario
          </Button>
          <p className="text-xs text-muted-foreground">
            Si ya tenías un plan activo, se sustituye (se borran sus sesiones
            futuras sin hacer).
          </p>
        </section>
      )}
    </div>
  );
}

/** Generar un plan de entrenamiento automático hacia un objetivo. */
export default function GenerarPlanPage() {
  return (
    <section className="mx-auto max-w-3xl space-y-4">
      <Link
        href="/plan"
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Plan
      </Link>
      <Card className="border-none bg-transparent shadow-none">
        <CardHeader className="px-0">
          <CardTitle className="font-heading text-2xl font-bold md:text-3xl">
            Crear plan de entrenamiento
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Un plan por fases hacia tu carrera, con tus ritmos y que se adapta
            cada semana a lo que haces y a cómo llegas.
          </p>
        </CardHeader>
      </Card>
      <Suspense fallback={<Skeleton className="h-64" />}>
        <Generator />
      </Suspense>
    </section>
  );
}
