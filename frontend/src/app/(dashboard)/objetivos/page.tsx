"use client";

import { Flag, Plus, Trophy } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGoals } from "@/hooks/use-api";
import { formatDate, formatDistance, formatDuration } from "@/lib/format";
import type { RaceGoal } from "@/types/api";

function GoalCard({ goal }: { goal: RaceGoal }) {
  const done = goal.result_time_s != null;
  const past = goal.days_left < 0;
  const gap =
    goal.target_time_s && goal.probable_s
      ? goal.probable_s - goal.target_time_s
      : null;
  return (
    <Link
      href={`/objetivos/${goal.id}`}
      className="block rounded-lg focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Card className="py-0 shadow-sm transition-colors hover:bg-muted/50">
        <CardContent className="flex flex-wrap items-center gap-3 p-4">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-md bg-muted text-klyp-accent">
            {done ? (
              <Trophy className="size-5" aria-hidden />
            ) : (
              <Flag className="size-5" aria-hidden />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{goal.name}</p>
            <p className="text-sm text-muted-foreground">
              {formatDistance(goal.distance_m)} ·{" "}
              {formatDate(`${goal.race_date}T12:00:00`)}
              {!past && ` · faltan ${goal.days_left} días`}
            </p>
          </div>
          <div className="text-right text-sm tabular-nums">
            {done ? (
              <>
                <p className="font-semibold">
                  {formatDuration(goal.result_time_s!)}
                </p>
                <p className="text-xs text-muted-foreground">resultado</p>
              </>
            ) : goal.probable_s ? (
              <>
                <p className="font-semibold">
                  {formatDuration(goal.probable_s)}
                </p>
                <p className="text-xs text-muted-foreground">
                  previsión
                  {gap != null &&
                    ` · ${gap > 0 ? "+" : "−"}${formatDuration(Math.abs(gap))} vs objetivo`}
                </p>
              </>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function ObjetivosPage() {
  const { data, isPending, isError, refetch } = useGoals();
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">
          Objetivos
        </h1>
        <Button asChild className="min-h-11">
          <Link href="/objetivos/nuevo">
            <Plus aria-hidden /> Nuevo objetivo
          </Link>
        </Button>
      </div>
      {isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar los objetivos."
          onRetry={() => refetch()}
        />
      ) : !data.length ? (
        <EmptyState icon={Flag} title="Aún no tienes objetivos">
          <p className="max-w-sm text-sm text-muted-foreground">
            Añade tu próxima carrera (5K, 10K, media o maratón) para ver tu
            previsión, lo que te falta y cómo prepararte.
          </p>
        </EmptyState>
      ) : (
        <div className="space-y-2">
          {data.map((g) => (
            <GoalCard key={g.id} goal={g} />
          ))}
        </div>
      )}
    </section>
  );
}
