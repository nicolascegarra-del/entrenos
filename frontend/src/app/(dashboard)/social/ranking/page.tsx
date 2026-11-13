"use client";

import {
  ArrowDown,
  ArrowUp,
  Minus,
  Sparkle,
  Swords,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { NewDuelDialog } from "@/components/social/duels";
import { PersonAvatar } from "@/components/social/person";
import { Segmented } from "@/components/social/segmented";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useLeaderboard } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import {
  formatMetric,
  gapText,
  METRIC_LABELS,
  ordinal,
  rankChange,
  SPORT_LABELS,
} from "@/lib/social";
import { cn } from "@/lib/utils";
import type {
  LeaderboardMetric,
  LeaderboardPeriod,
  LeaderboardRow,
  PersonRef,
  SocialSport,
} from "@/types/api";

const CHANGE_ICON = {
  up: ArrowUp,
  down: ArrowDown,
  same: Minus,
  new: Sparkle,
} as const;

const CHANGE_COLOR = {
  up: "text-emerald-700 dark:text-emerald-400",
  down: "text-red-700 dark:text-red-400",
  same: "text-muted-foreground",
  new: "text-klyp-accent",
} as const;

/** Cambio de puesto con icono y texto (no solo color). */
function Change({ row }: { row: LeaderboardRow }) {
  const c = rankChange(row.rank, row.prev_rank);
  const Icon = CHANGE_ICON[c.dir];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs",
        CHANGE_COLOR[c.dir],
      )}
      title={c.label}
    >
      <Icon className="size-3.5" aria-hidden />
      <span aria-hidden>
        {c.dir === "up" || c.dir === "down"
          ? c.steps
          : c.dir === "new"
            ? "Nuevo"
            : "="}
      </span>
      <span className="sr-only">{c.label}</span>
    </span>
  );
}

/** Clasificación entre tú y quien sigues: semana o mes, por métrica y deporte. */
export default function RankingPage() {
  const [period, setPeriod] = useState<LeaderboardPeriod>("week");
  const [metric, setMetric] = useState<LeaderboardMetric>("km");
  const [sport, setSport] = useState<SocialSport>("all");
  const [rival, setRival] = useState<PersonRef | null>(null);
  const { data, isPending, isError, refetch } = useLeaderboard(
    period,
    metric,
    sport,
  );
  const gap = data
    ? gapText(data.metric, data.gap_to_next, data.next_name)
    : null;

  return (
    <section className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="Clasificación"
        subtitle="Entre tú y la gente que sigues"
        hideTitleOnMobile
      />
      <div className="space-y-2">
        <Segmented
          label="Periodo"
          value={period}
          options={[
            { value: "week", label: "Semana" },
            { value: "month", label: "Mes" },
          ]}
          onChange={setPeriod}
        />
        <Segmented
          label="Métrica"
          value={metric}
          options={(["km", "time", "elevation", "days"] as const).map((m) => ({
            value: m,
            label: METRIC_LABELS[m],
          }))}
          onChange={setMetric}
        />
        <Segmented
          label="Deporte"
          value={sport}
          options={(["all", "running", "cycling"] as const).map((s) => ({
            value: s,
            label: SPORT_LABELS[s],
          }))}
          onChange={setSport}
        />
      </div>

      {isPending ? (
        <div
          className="space-y-2"
          role="status"
          aria-label="Cargando clasificación"
        >
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar la clasificación."
          onRetry={() => refetch()}
        />
      ) : data.rows.length <= 1 ? (
        <EmptyState icon={Trophy} title="Necesitas rivales">
          <p className="max-w-sm text-sm text-muted-foreground">
            La clasificación es entre tú y la gente que sigues. Sigue a tus
            amigos para ver quién suma más.
          </p>
          <Button asChild className="min-h-11">
            <Link href="/social/personas">Buscar personas</Link>
          </Button>
        </EmptyState>
      ) : (
        <>
          <p className="text-sm" aria-live="polite">
            {data.my_rank === 1 ? (
              <strong>¡Vas primero! Que no te pillen.</strong>
            ) : gap ? (
              <>
                {data.my_rank && <strong>Vas {ordinal(data.my_rank)}. </strong>}
                {gap}.
              </>
            ) : null}
            <span className="block text-xs text-muted-foreground">
              Del {formatDate(data.period_start)} al{" "}
              {formatDate(data.period_end)}
            </span>
          </p>
          <Card className="gap-0 py-0 shadow-sm">
            <CardContent className="p-0">
              <ol aria-label="Clasificación" className="divide-y">
                {data.rows.map((row) => (
                  <li
                    key={row.user_id}
                    aria-current={row.me ? "true" : undefined}
                    className={cn(
                      "flex items-center gap-2 px-3 py-2 md:gap-3 md:px-4",
                      row.me &&
                        "bg-klyp-accent/10 ring-1 ring-klyp-accent/40 ring-inset",
                    )}
                  >
                    <span className="w-8 shrink-0 text-center font-heading text-lg font-bold tabular-nums">
                      {row.rank}
                      <span className="sr-only">.º puesto</span>
                    </span>
                    <span className="w-12 shrink-0">
                      <Change row={row} />
                    </span>
                    <PersonAvatar name={row.display_name} size="sm" />
                    <Link
                      href={`/u/${row.handle}`}
                      className="min-w-0 flex-1 hover:underline"
                    >
                      <span className="block truncate font-medium">
                        {row.me ? `${row.display_name} (tú)` : row.display_name}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        @{row.handle}
                      </span>
                    </Link>
                    <span className="shrink-0 text-right font-semibold tabular-nums">
                      {formatMetric(data.metric, row.value)}
                    </span>
                    {row.me ? (
                      <span className="w-11 shrink-0 md:w-20" aria-hidden />
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="min-h-11 w-11 shrink-0 px-0 md:min-h-8 md:w-20 md:px-2"
                        aria-label={`Retar a ${row.display_name}`}
                        onClick={() => setRival(row)}
                      >
                        <Swords aria-hidden />
                        <span className="max-md:hidden">Retar</span>
                      </Button>
                    )}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </>
      )}
      <NewDuelDialog
        key={rival?.user_id ?? "none"}
        open={!!rival}
        onOpenChange={(o) => !o && setRival(null)}
        opponent={rival ?? undefined}
      />
    </section>
  );
}
