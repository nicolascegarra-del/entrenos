"use client";

import { CalendarPlus, ChevronRight, Clock, Flag } from "lucide-react";
import Link from "next/link";

import { InfoTerm } from "@/components/glossary/info-term";
import { ScoreBadge } from "@/components/plan/status-badge";
import { INSIGHT_STATUS } from "@/components/progress/insight";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDistance, formatDuration, sportInfo } from "@/lib/format";
import { nextGoal } from "@/lib/summary";
import { cn } from "@/lib/utils";
import type { RaceGoal, Summary } from "@/types/api";

function daysText(days: number) {
  if (days === 0) return "es hoy";
  if (days === 1) return "mañana";
  return `en ${days} días`;
}

/**
 * Tarjeta principal del Resumen: responde a «¿qué hago hoy?» con el estado de
 * frescura, la sesión planificada y el próximo objetivo.
 */
export function TodayCard({
  summary,
  goals,
  today,
}: {
  summary: Summary;
  goals: RaceGoal[] | undefined;
  /** Día local en ISO (YYYY-MM-DD). */
  today: string;
}) {
  const { readiness } = summary;
  const status = INSIGHT_STATUS[readiness.status];
  const sessions = summary.planned_this_week.filter((p) => p.day === today);
  const goal = nextGoal(goals);
  const weekday = new Date(`${today}T12:00:00`).toLocaleDateString("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <Card className="shadow-md">
      <CardHeader>
        <CardTitle className="font-heading text-lg">
          <span className="capitalize">{weekday}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        {/* Cómo llegas */}
        <div className={cn("rounded-lg border p-3", status.className)}>
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <status.icon className="size-4" aria-hidden />
            Cómo llegas
            <span className="sr-only">: {status.label}</span>
            <InfoTerm term="tsb" className="text-current" />
          </p>
          <p className="mt-1 text-lg font-semibold">{readiness.title}</p>
          <p className="text-sm">{readiness.message}</p>
        </div>

        {/* Qué toca */}
        <div className="rounded-lg bg-muted/60 p-3">
          <p className="text-xs font-medium text-muted-foreground">Qué toca</p>
          {sessions.length ? (
            <ul className="mt-1 space-y-1">
              {sessions.map((p) => {
                const { icon: Icon } = sportInfo(p.sport);
                return (
                  <li key={p.id}>
                    <Link
                      href={`/plan/${p.id}`}
                      className="-mx-1 flex min-h-11 items-center gap-2 rounded-md px-1 hover:bg-muted"
                    >
                      <Icon
                        className="size-5 shrink-0 text-klyp-accent"
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate font-medium">
                        {p.title}
                      </span>
                      {p.compliance_score != null ? (
                        <ScoreBadge score={p.compliance_score} />
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="size-3" aria-hidden /> Pendiente
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <>
              <p className="mt-1 text-lg font-semibold">Sin sesión</p>
              <p className="text-sm text-muted-foreground">
                Día libre o entreno a tu aire.
              </p>
              <Button
                asChild
                variant="outline"
                size="sm"
                className="mt-2 min-h-11 md:min-h-8"
              >
                <Link href="/plan/nueva">
                  <CalendarPlus aria-hidden /> Planificar una
                </Link>
              </Button>
            </>
          )}
        </div>

        {/* Hacia dónde vas */}
        <div className="rounded-lg bg-muted/60 p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Tu objetivo
          </p>
          {goal ? (
            <Link
              href={`/objetivos/${goal.id}`}
              className="-mx-1 mt-1 flex items-center gap-2 rounded-md px-1 py-1 hover:bg-muted"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold">
                  {goal.name}
                </span>
                <span className="block text-sm text-muted-foreground">
                  {formatDistance(goal.distance_m)} · {daysText(goal.days_left)}
                </span>
                {goal.probable_s != null && (
                  <span className="block text-sm tabular-nums">
                    Previsión {formatDuration(goal.probable_s)}
                    {goal.target_time_s != null && (
                      <span className="text-muted-foreground">
                        {" "}
                        · objetivo {formatDuration(goal.target_time_s)}
                      </span>
                    )}
                  </span>
                )}
              </span>
              <ChevronRight
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
            </Link>
          ) : (
            <>
              <p className="mt-1 text-lg font-semibold">Sin objetivo</p>
              <Button
                asChild
                variant="outline"
                size="sm"
                className="mt-2 min-h-11 md:min-h-8"
              >
                <Link href="/objetivos/nuevo">
                  <Flag aria-hidden /> Crear un objetivo
                </Link>
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
