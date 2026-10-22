"use client";

import {
  ArrowLeft,
  CircleCheck,
  CircleDashed,
  Pencil,
  Trash2,
  TriangleAlert,
  Trophy,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  ForecastExplanation,
  PacesExplanationBlock,
} from "@/components/goals/explanation";
import { TimeChart } from "@/components/progress/time-chart";
import { ErrorState } from "@/components/states";
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
  useDeleteGoal,
  useGoalCandidates,
  useGoalReport,
  useGoalResult,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GoalReport, PaceZone } from "@/types/api";

const t = (iso: string) => new Date(`${iso}T12:00:00`).getTime();

const PACE_LABELS: { key: PaceZone; label: string; hint: string }[] = [
  { key: "easy", label: "E · Suave", hint: "Rodajes y tiradas largas" },
  { key: "marathon", label: "M · Maratón", hint: "Ritmo de maratón" },
  { key: "threshold", label: "T · Umbral", hint: "Tempo y series largas" },
  { key: "interval", label: "I · Intervalos", hint: "Series de 3–5 min" },
  {
    key: "repetition",
    label: "R · Repeticiones",
    hint: "Series cortas y rápidas",
  },
];

const CHECK_ICON = {
  ok: {
    icon: CircleCheck,
    className: "text-emerald-600 dark:text-emerald-400",
    label: "Cumplido",
  },
  pending: {
    icon: CircleDashed,
    className: "text-muted-foreground",
    label: "Pendiente",
  },
  warn: {
    icon: TriangleAlert,
    className: "text-amber-600 dark:text-amber-400",
    label: "Atención",
  },
};

/** Barra del rango previsto con la marca del objetivo. */
function RangeBar({ report }: { report: GoalReport }) {
  const {
    optimistic_s: lo,
    probable_s: mid,
    conservative_s: hi,
  } = report.forecast;
  const target = report.goal.target_time_s;
  if (lo == null || hi == null || mid == null) return null;
  const min = Math.min(lo, target ?? lo);
  const max = Math.max(hi, target ?? hi);
  const pad = (max - min) * 0.08 || 30;
  const pos = (v: number) => ((v - (min - pad)) / (max - min + 2 * pad)) * 100;
  return (
    <div className="space-y-1" aria-hidden>
      <div className="relative h-8">
        <div className="absolute top-3 h-2 w-full rounded-full bg-muted" />
        <div
          className="absolute top-3 h-2 rounded-full bg-klyp-accent/40"
          style={{ left: `${pos(lo)}%`, width: `${pos(hi) - pos(lo)}%` }}
        />
        <div
          className="absolute top-1.5 size-5 -translate-x-1/2 rounded-full border-2 border-card bg-klyp-accent"
          style={{ left: `${pos(mid)}%` }}
        />
        {target && (
          <div
            className="absolute top-0 h-8 w-0.5 -translate-x-1/2 bg-foreground"
            style={{ left: `${pos(target)}%` }}
          />
        )}
      </div>
      <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>Optimista {formatDuration(lo)}</span>
        <span>Conservadora {formatDuration(hi)}</span>
      </div>
    </div>
  );
}

function ForecastCard({ report }: { report: GoalReport }) {
  const { forecast: f, goal, gap_s: gap } = report;
  if (f.probable_s == null) {
    return (
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Previsión</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {f.warnings.join(" ")}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Previsión de hoy</CardTitle>
        <CardDescription>
          {f.calibration_factor
            ? `Calibrada con tus carreras reales (×${formatNumber(f.calibration_factor, 3)}).`
            : "Sin calibrar todavía: marca tus carreras reales para afinarla."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <div>
            <p className="text-xs text-muted-foreground">Tiempo probable</p>
            <p className="text-4xl font-bold tabular-nums">
              {formatDuration(f.probable_s)}
            </p>
            <p className="text-sm text-muted-foreground tabular-nums">
              {formatDuration((f.probable_s / goal.distance_m) * 1000)} /km
            </p>
          </div>
          {goal.target_time_s && gap != null && (
            <div>
              <p className="text-xs text-muted-foreground">
                Objetivo {formatDuration(goal.target_time_s)}
              </p>
              <p
                className={cn(
                  "text-xl font-semibold tabular-nums",
                  gap <= 0 ? "text-emerald-700 dark:text-emerald-400" : "",
                )}
              >
                {gap <= 0
                  ? `Vas ${formatDuration(-gap)} por delante`
                  : `Te faltan ${formatDuration(gap)}`}
              </p>
              {report.vdot_needed && f.vdot_current && (
                <p className="text-sm text-muted-foreground tabular-nums">
                  VDOT necesario {formatNumber(report.vdot_needed, 1)} · actual{" "}
                  {formatNumber(f.vdot_current, 1)}
                  {f.vdot_source === "vo2max" && " (desde VO2max)"}
                </p>
              )}
            </div>
          )}
          {report.age_grade?.probable && (
            <div>
              <p className="text-xs text-muted-foreground">
                Ajustado por edad ({report.age_grade.age} años)
              </p>
              <p className="text-xl font-semibold tabular-nums">
                {formatNumber(report.age_grade.probable.percent, 1)} %
              </p>
              <p className="text-sm text-muted-foreground">
                {report.age_grade.probable.level}
                {report.age_grade.target &&
                  ` · tu objetivo sería ${formatNumber(report.age_grade.target.percent, 1)} %`}
              </p>
            </div>
          )}
        </div>
        <RangeBar report={report} />

        {f.warnings.length > 0 && (
          <ul className="space-y-1.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200">
            {f.warnings.map((w) => (
              <li key={w} className="flex gap-2">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{" "}
                {w}
              </li>
            ))}
          </ul>
        )}

        <details className="text-sm">
          <summary className="cursor-pointer font-medium">
            Cómo se calcula
          </summary>
          <ul className="mt-2 space-y-1">
            {f.models.map((m) => (
              <li
                key={m.key}
                className="flex flex-wrap justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 tabular-nums"
              >
                <span>
                  {m.label}{" "}
                  <span className="text-muted-foreground">· {m.detail}</span>
                </span>
                <span>
                  {formatDuration(m.time_s)}{" "}
                  <span className="text-muted-foreground">
                    ({Math.round(m.weight * 100)} %)
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Riegel 1981 (exponente{" "}
            {f.exponent_personal ? "personal" : "estándar"}), Daniels y Gilbert
            (VDOT) y Tanda 2011 para maratón. El rango refleja cuánto discrepan
            los modelos y la incertidumbre de la distancia.
          </p>
        </details>
      </CardContent>
    </Card>
  );
}

function ChecklistCard({ report }: { report: GoalReport }) {
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Preparación</CardTitle>
        <CardDescription>
          {report.weeks_left > 0
            ? `Quedan ${formatNumber(report.weeks_left, 1)} semanas.`
            : "La carrera ya ha pasado."}{" "}
          Valores orientativos para un corredor popular.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {report.checklist.map((item) => {
            const { icon: Icon, className, label } = CHECK_ICON[item.status];
            return (
              <li
                key={item.key}
                className="flex gap-3 rounded-md bg-muted/60 p-3 text-sm"
              >
                <Icon
                  className={cn("mt-0.5 size-5 shrink-0", className)}
                  aria-label={label}
                />
                <span>
                  <span className="block font-medium">{item.label}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {item.current}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function PacesCard({ report }: { report: GoalReport }) {
  if (!report.paces) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">
          Tus ritmos de entrenamiento
        </CardTitle>
        <CardDescription>
          Según tu VDOT actual (Daniels). El planificador los usa
          automáticamente.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1 text-sm">
          {PACE_LABELS.map(({ key, label, hint }) => (
            <li
              key={key}
              className="flex items-center justify-between gap-2 rounded-md bg-muted/60 px-3 py-2"
            >
              <span>
                <span className="font-medium">{label}</span>{" "}
                <span className="text-xs text-muted-foreground">{hint}</span>
              </span>
              <span className="tabular-nums">
                {formatDuration(report.paces![key][0])}–
                {formatDuration(report.paces![key][1])} /km
              </span>
            </li>
          ))}
        </ul>
        {report.paces_explanation && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium">
              ¿De dónde salen estos ritmos?
            </summary>
            <div className="mt-2">
              <PacesExplanationBlock explanation={report.paces_explanation} />
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function ResultCard({ report }: { report: GoalReport }) {
  const { goal } = report;
  const raceDone = goal.days_left <= 0;
  const [choosing, setChoosing] = useState(false);
  const candidates = useGoalCandidates(goal.id, choosing);
  const result = useGoalResult(goal.id);
  if (!raceDone && goal.result_time_s == null) return null;

  const mark = (activityId: number | null) =>
    result.mutate(activityId, {
      onSuccess: () => {
        setChoosing(false);
        toast.success(
          activityId
            ? "Carrera registrada: las previsiones se recalibran"
            : "Resultado quitado",
        );
      },
      onError: (err) =>
        toast.error(
          err instanceof ApiError ? err.message : "No se pudo guardar.",
        ),
    });

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Trophy className="size-5 text-klyp-accent" aria-hidden /> Resultado
        </CardTitle>
        <CardDescription>
          Marca la actividad de la carrera: la diferencia con la previsión
          calibra las siguientes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {goal.result_time_s != null ? (
          <>
            <p className="text-2xl font-bold tabular-nums">
              {formatDuration(goal.result_time_s)}
            </p>
            {goal.predicted_time_s && (
              <p className="text-muted-foreground tabular-nums">
                La app preveía {formatDuration(goal.predicted_time_s)} (
                {goal.result_time_s <= goal.predicted_time_s
                  ? "fuiste "
                  : "fuiste "}
                {formatNumber(
                  (Math.abs(goal.result_time_s - goal.predicted_time_s) /
                    goal.predicted_time_s) *
                    100,
                  1,
                )}{" "}
                %{" "}
                {goal.result_time_s <= goal.predicted_time_s
                  ? "más rápido"
                  : "más lento"}
                ).
              </p>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() => mark(null)}
            >
              Quitar resultado
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => setChoosing((v) => !v)}
            >
              Marcar la actividad de la carrera
            </Button>
            {choosing &&
              (candidates.isPending ? (
                <Skeleton className="h-12 w-full" />
              ) : candidates.data?.length ? (
                candidates.data.map((a) => (
                  <Button
                    key={a.id}
                    variant="outline"
                    className="h-auto min-h-11 w-full justify-start py-2 text-left"
                    onClick={() => mark(a.id)}
                  >
                    <span className="tabular-nums">
                      {formatDateTime(a.start_time)} ·{" "}
                      {formatDistance(a.distance_m)} ·{" "}
                      {formatDuration(a.duration_s)}
                    </span>
                  </Button>
                ))
              ) : (
                <p className="text-muted-foreground">
                  No hay carreras sincronizadas ese día.
                </p>
              ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function ObjetivoPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { data, isPending, isError, error, refetch } = useGoalReport(id);
  const remove = useDeleteGoal();

  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Cargando objetivo">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <ErrorState
        message={
          notFound
            ? "Este objetivo no existe."
            : "No se pudo cargar el objetivo."
        }
        onRetry={notFound ? undefined : () => refetch()}
      />
    );
  }

  const { goal } = data;
  const evolution = data.evolution.map((p) => ({
    t: t(p.day),
    probable: p.probable_s,
    optimistic: p.optimistic_s,
    conservative: p.conservative_s,
  }));
  return (
    <article className="space-y-4 md:space-y-6">
      <header className="space-y-2">
        <Link
          href="/objetivos"
          className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden /> Objetivos
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-heading text-2xl font-bold md:text-3xl">
              {goal.name}
            </h1>
            <p className="text-sm text-muted-foreground">
              {formatDistance(goal.distance_m)} ·{" "}
              {formatDate(`${goal.race_date}T12:00:00`)}
              {goal.days_left > 0
                ? ` · faltan ${goal.days_left} días`
                : goal.days_left === 0
                  ? " · ¡es hoy!"
                  : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {goal.days_left > 0 && goal.result_time_s == null && (
              <Button asChild className="min-h-11">
                <Link href={`/plan/generar?objetivo=${goal.id}`}>
                  <Sparkles aria-hidden /> Crear plan de entrenamiento
                </Link>
              </Button>
            )}
            <Button asChild variant="outline" className="min-h-11">
              <Link href={`/objetivos/${goal.id}/editar`}>
                <Pencil aria-hidden /> Editar
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-11 text-destructive"
              aria-label="Borrar objetivo"
              onClick={() => {
                if (!window.confirm("¿Borrar este objetivo?")) return;
                remove.mutate(goal.id, {
                  onSuccess: () => router.push("/objetivos"),
                });
              }}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
      </header>

      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <div className="space-y-4 md:space-y-6 lg:col-span-2">
          <ForecastCard report={data} />
          <ForecastExplanation explanation={data.explanation} />
        </div>
        <ResultCard report={data} />
        {evolution.length >= 2 && (
          <Card className="shadow-sm lg:col-span-2">
            <CardHeader>
              <CardTitle className="font-heading text-lg">
                Evolución de la previsión
              </CardTitle>
              <CardDescription>
                Calculada cada domingo con los datos que tenías hasta ese día
                (menos es mejor).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TimeChart
                data={evolution}
                format={(v) => formatDuration(v)}
                refLine={
                  goal.target_time_s
                    ? { y: goal.target_time_s, label: "objetivo" }
                    : undefined
                }
                series={[
                  {
                    key: "conservative",
                    label: "Conservadora",
                    color: "var(--chart-5)",
                    kind: "line",
                  },
                  {
                    key: "probable",
                    label: "Probable",
                    color: "var(--chart-1)",
                    kind: "line",
                  },
                  {
                    key: "optimistic",
                    label: "Optimista",
                    color: "var(--chart-3)",
                    kind: "line",
                  },
                ]}
              />
            </CardContent>
          </Card>
        )}
        <ChecklistCard report={data} />
        <PacesCard report={data} />
      </div>
    </article>
  );
}
