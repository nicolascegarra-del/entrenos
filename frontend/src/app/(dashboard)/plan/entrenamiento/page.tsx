"use client";

import {
  CircleCheck,
  CircleDashed,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ScoreBadge } from "@/components/plan/status-badge";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivePlan, useAdaptPlan, useCancelPlan } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import { ACTION_LABEL, PHASE_HELP, WEEKDAY_SHORT } from "@/lib/training-plan";
import { cn } from "@/lib/utils";
import type { TrainingPlanWeekOut } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

function WeekCard({ w }: { w: TrainingPlanWeekOut }) {
  const pct = w.target_km ? Math.min(100, (w.done_km / w.target_km) * 100) : 0;
  return (
    <li
      className={cn(
        "space-y-2 rounded-lg border p-3",
        w.is_current && "border-klyp-accent shadow-sm",
      )}
      aria-current={w.is_current ? "step" : undefined}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Semana {w.index}</span>
        <Badge variant="outline" title={PHASE_HELP[w.phase]}>
          {w.phase_label}
        </Badge>
        {w.is_recovery && <Badge variant="secondary">Descarga</Badge>}
        {w.is_current && <Badge>Esta semana</Badge>}
        <span className="ml-auto text-xs text-muted-foreground">
          desde {formatDate(`${w.start}T12:00:00`)}
        </span>
      </div>
      <div>
        <div className="flex justify-between text-xs tabular-nums">
          <span>
            {formatNumber(w.done_km, 1)} de {formatNumber(w.target_km, 1)} km
          </span>
          <span className="text-muted-foreground">{Math.round(pct)} %</span>
        </div>
        <div
          className="mt-1 h-2 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Kilómetros de la semana ${w.index}`}
        >
          <div className="h-full bg-klyp-accent" style={{ width: `${pct}%` }} />
        </div>
      </div>
      {w.adjustment && (
        <p className="rounded-md bg-muted/60 p-2 text-sm">
          <strong>{ACTION_LABEL[w.adjustment.action]}</strong>:{" "}
          {w.adjustment.reason}
        </p>
      )}
      {w.sessions.length > 0 && (
        <ul className="space-y-1">
          {w.sessions.map((s) => (
            <li key={s.id}>
              <Link
                href={`/plan/${s.id}`}
                className="flex min-h-11 items-center gap-2 rounded-md px-2 text-sm hover:bg-muted"
              >
                {s.done ? (
                  <CircleCheck
                    className="size-4 shrink-0 text-emerald-600"
                    aria-label="Hecha"
                  />
                ) : (
                  <CircleDashed
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-label="Pendiente"
                  />
                )}
                <span className="w-6 text-xs text-muted-foreground">
                  {
                    WEEKDAY_SHORT[
                      (new Date(`${s.day}T12:00:00`).getDay() + 6) % 7
                    ]
                  }
                </span>
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
                {s.compliance != null && <ScoreBadge score={s.compliance} />}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Plan de entrenamiento activo: semanas, progreso y ajustes semanales. */
export default function EntrenamientoPage() {
  const router = useRouter();
  const { data: plan, isPending, isError, refetch } = useActivePlan();
  const adapt = useAdaptPlan();
  const cancel = useCancelPlan();

  return (
    <section className="mx-auto max-w-3xl space-y-4">
      {isPending ? (
        <Skeleton className="h-64" />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar tu plan."
          onRetry={() => refetch()}
        />
      ) : !plan ? (
        <EmptyState icon={Sparkles} title="No tienes un plan activo">
          <p className="max-w-sm text-sm text-muted-foreground">
            Genera un plan por fases hacia tu próximo objetivo, con tus ritmos.
          </p>
          <Button asChild className="mt-2 min-h-11">
            <Link href="/plan/generar">Crear plan de entrenamiento</Link>
          </Button>
        </EmptyState>
      ) : (
        <>
          <header className="space-y-1">
            <h1 className="font-heading text-2xl font-bold md:text-3xl">
              {plan.goal_name ?? "Plan de entrenamiento"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {plan.current_week
                ? `Semana ${plan.current_week} de ${plan.total_weeks}`
                : `${plan.total_weeks} semanas`}{" "}
              · carrera el {formatDate(`${plan.race_date}T12:00:00`)}
              {plan.vdot
                ? ` · nivel de carrera ${formatNumber(plan.vdot, 1)}`
                : ""}
            </p>
          </header>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="min-h-11 md:min-h-9"
              disabled={adapt.isPending}
              onClick={() =>
                adapt.mutate(plan.id, {
                  onSuccess: (res) =>
                    toast.success(
                      res.adjustment
                        ? res.adjustment.reason
                        : "No hay semana que ajustar ahora.",
                    ),
                  onError: (err) => toast.error(errorText(err)),
                })
              }
            >
              {adapt.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCw aria-hidden />
              )}
              Revisar el plan ahora
            </Button>
            <Button
              variant="ghost"
              className="min-h-11 text-destructive md:min-h-9"
              disabled={cancel.isPending}
              onClick={() => {
                if (
                  !window.confirm(
                    "¿Cancelar el plan? Se borran sus sesiones futuras sin hacer; las hechas se conservan.",
                  )
                )
                  return;
                cancel.mutate(plan.id, {
                  onSuccess: () => {
                    toast.success("Plan cancelado.");
                    router.push("/plan");
                  },
                  onError: (err) => toast.error(errorText(err)),
                });
              }}
            >
              <Trash2 aria-hidden /> Cancelar plan
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Cada lunes el plan revisa la semana anterior (sesiones hechas y
            cumplimiento) y cómo llegas (frescura y carga reciente): progresa,
            mantiene o baja la carga, y actualiza tus ritmos. Si editas una
            sesión a mano, la revisión semanal puede reemplazarla.
          </p>
          <ol className="space-y-3">
            {plan.weeks.map((w) => (
              <WeekCard key={w.index} w={w} />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
