"use client";

import { ArrowLeft, Link2, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { RepsChart } from "@/components/plan/reps-chart";
import { ScoreBadge, StatusBadge } from "@/components/plan/status-badge";
import { ErrorState } from "@/components/states";
import { SendToWatchCard } from "@/components/plan/send-to-watch";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDeletePlan,
  usePlan,
  usePlanCandidates,
  useSetMatch,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  formatDistance,
  formatDuration,
  sportInfo,
} from "@/lib/format";
import {
  BLOCK_KINDS,
  DIRECTION_LABEL,
  blockSummary,
  formatTarget,
  formatTargetValue,
  metricInfo,
} from "@/lib/plan";
import type { ComplianceStep, PlannedSessionDetail } from "@/types/api";

function plannedLabel(step: ComplianceStep): string {
  const { planned } = step;
  const quantity = planned.distance_m
    ? formatDistance(planned.distance_m)
    : planned.duration_s
      ? formatDuration(planned.duration_s)
      : "libre";
  const target = planned.target_metric
    ? ` @ ${formatTarget(planned.target_metric, planned.target_min, planned.target_max)}`
    : "";
  return quantity + target;
}

function actualLabel(step: ComplianceStep): string {
  const { actual, planned } = step;
  const quantity = planned.distance_m
    ? formatDistance(actual.distance_m)
    : formatDuration(actual.duration_s);
  if (!planned.target_metric || actual.value == null) return quantity;
  return `${quantity} @ ${formatTargetValue(planned.target_metric, actual.value)} ${metricInfo(planned.target_metric).unit}`;
}

function MatchPanel({ plan }: { plan: PlannedSessionDetail }) {
  const [choosing, setChoosing] = useState(false);
  const candidates = usePlanCandidates(plan.id, choosing);
  const setMatch = useSetMatch(plan.id);
  const run = (body: {
    mode: "auto" | "manual";
    activity_id?: number | null;
  }) =>
    setMatch.mutate(body, {
      onSuccess: () => setChoosing(false),
      onError: (err) =>
        toast.error(
          err instanceof ApiError
            ? err.message
            : "No se pudo cambiar la actividad.",
        ),
    });

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">
          Actividad realizada
        </CardTitle>
        <CardDescription>
          {plan.match_mode === "auto"
            ? "Emparejada automáticamente por día y deporte."
            : "Elegida a mano."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {plan.activity ? (
          <Link
            href={`/actividades/${plan.activity.id}`}
            className="block rounded-md bg-muted/60 p-3 hover:bg-muted"
          >
            <p className="font-medium">
              {plan.activity.name || sportInfo(plan.activity.sport).label}
            </p>
            <p className="text-sm text-muted-foreground tabular-nums">
              {formatDateTime(plan.activity.start_time)} ·{" "}
              {formatDistance(plan.activity.distance_m)} ·{" "}
              {formatDuration(plan.activity.duration_s)}
            </p>
          </Link>
        ) : (
          <p className="text-sm text-muted-foreground">
            Aún no hay actividad de ese día. Se emparejará sola al sincronizar
            con Garmin.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 md:min-h-8"
            onClick={() => setChoosing((v) => !v)}
          >
            <Link2 aria-hidden /> Cambiar actividad
          </Button>
          {plan.match_mode === "manual" && (
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() => run({ mode: "auto" })}
            >
              Volver a automático
            </Button>
          )}
          {plan.activity && (
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() => run({ mode: "manual", activity_id: null })}
            >
              Desvincular
            </Button>
          )}
        </div>
        {choosing && (
          <div className="space-y-2">
            {candidates.isPending ? (
              <Skeleton className="h-12 w-full" />
            ) : candidates.data?.length ? (
              candidates.data.map((a) => (
                <Button
                  key={a.id}
                  variant="outline"
                  className="h-auto min-h-11 w-full justify-start py-2 text-left"
                  onClick={() => run({ mode: "manual", activity_id: a.id })}
                >
                  <span className="tabular-nums">
                    {formatDateTime(a.start_time)} ·{" "}
                    {formatDistance(a.distance_m)} ·{" "}
                    {formatDuration(a.duration_s)}
                  </span>
                </Button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                No hay otras actividades de ese día y deporte.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ComplianceTable({ steps }: { steps: ComplianceStep[] }) {
  return (
    <>
      {/* Móvil: tarjetas apiladas */}
      <ol className="space-y-2 md:hidden">
        {steps.map((s, i) => (
          <li key={i} className="rounded-md border border-border p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{s.label}</span>
              {s.status && (
                <StatusBadge status={s.status}>
                  {s.score != null ? `${Math.round(s.score)} %` : undefined}
                </StatusBadge>
              )}
            </div>
            <p className="mt-1 text-muted-foreground tabular-nums">
              Plan: {plannedLabel(s)}
            </p>
            <p className="tabular-nums">
              Real: {actualLabel(s)}
              {s.direction && (
                <span className="text-muted-foreground">
                  {" "}
                  · {DIRECTION_LABEL[s.direction]}
                </span>
              )}
            </p>
          </li>
        ))}
      </ol>
      {/* Escritorio: tabla */}
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Paso</TableHead>
              <TableHead>Plan</TableHead>
              <TableHead>Real</TableHead>
              <TableHead>Vueltas</TableHead>
              <TableHead className="text-right">Estado</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {steps.map((s, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{s.label}</TableCell>
                <TableCell className="tabular-nums">
                  {plannedLabel(s)}
                </TableCell>
                <TableCell className="tabular-nums">
                  {actualLabel(s)}
                  {s.direction && (
                    <span className="text-muted-foreground">
                      {" "}
                      · {DIRECTION_LABEL[s.direction]}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground tabular-nums">
                  {s.actual.laps.length
                    ? s.actual.laps.map((l) => l + 1).join(", ")
                    : "—"}
                </TableCell>
                <TableCell className="text-right">
                  {s.status && (
                    <StatusBadge status={s.status}>
                      {s.score != null ? `${Math.round(s.score)} %` : undefined}
                    </StatusBadge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

export default function PlanDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { data: plan, isPending, isError, error, refetch } = usePlan(id);
  const remove = useDeletePlan();

  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Cargando sesión">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <ErrorState
        message={
          notFound ? "Esta sesión no existe." : "No se pudo cargar la sesión."
        }
        onRetry={notFound ? undefined : () => refetch()}
      />
    );
  }

  const detail = plan.compliance_detail;
  const steps = detail.steps ?? [];
  const reps = steps.filter(
    (s) => s.kind === "interval" && s.planned.target_metric,
  );
  const repMetric = reps[0]?.planned.target_metric;
  const showRepsChart =
    repMetric &&
    reps.length >= 2 &&
    reps.every((s) => s.planned.target_metric === repMetric);
  const kindLabel = (kind: string) =>
    BLOCK_KINDS.find((k) => k.value === kind)?.label ?? kind;

  return (
    <article className="space-y-4 md:space-y-6">
      <header className="space-y-2">
        <Link
          href="/plan"
          className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden /> Plan
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-heading text-2xl font-bold md:text-3xl">
              {plan.title}
            </h1>
            <p className="text-sm text-muted-foreground">
              {formatDate(`${plan.day}T12:00:00`)} ·{" "}
              {sportInfo(plan.sport).label}
            </p>
          </div>
          <div className="flex gap-2">
            <Button asChild variant="outline" className="min-h-11">
              <Link href={`/plan/${plan.id}/editar`}>
                <Pencil aria-hidden /> Editar
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-11 text-destructive"
              aria-label="Borrar sesión"
              onClick={() => {
                if (!window.confirm("¿Borrar esta sesión planificada?")) return;
                remove.mutate(plan.id, {
                  onSuccess: () => {
                    toast.success("Sesión borrada");
                    router.push("/plan");
                  },
                });
              }}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
      </header>

      <SendToWatchCard plan={plan} />

      <div className="grid gap-4 md:gap-6 lg:grid-cols-[1fr_22rem]">
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <div className="space-y-1">
              <CardTitle className="font-heading text-lg">
                Plan vs real
              </CardTitle>
              <CardDescription>
                {detail.method === "laps"
                  ? "Comparado vuelta a vuelta con lo que marcaste en el reloj."
                  : detail.method === "streams"
                    ? "Sin vueltas: estimado recorriendo la actividad por distancia y tiempo."
                    : "Se calculará cuando haya una actividad emparejada."}
              </CardDescription>
            </div>
            {plan.compliance_score != null && (
              <div className="text-right">
                <p className="text-3xl font-bold tabular-nums">
                  {Math.round(plan.compliance_score)}%
                </p>
                <ScoreBadge score={plan.compliance_score} />
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {steps.length ? (
              <>
                {showRepsChart && <RepsChart steps={reps} metric={repMetric} />}
                <ComplianceTable steps={steps} />
                {!!detail.unplanned_laps?.length && (
                  <p className="text-xs text-muted-foreground">
                    Vueltas fuera del plan:{" "}
                    {detail.unplanned_laps.map((l) => l + 1).join(", ")}.
                  </p>
                )}
              </>
            ) : (
              <ul className="space-y-2 text-sm">
                {plan.blocks.map((b) => (
                  <li key={b.position} className="rounded-md bg-muted/60 p-3">
                    <span className="font-medium">{kindLabel(b.kind)}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {blockSummary(b)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {plan.notes && (
              <p className="text-sm whitespace-pre-line text-muted-foreground">
                {plan.notes}
              </p>
            )}
          </CardContent>
        </Card>
        <MatchPanel plan={plan} />
      </div>
    </article>
  );
}
