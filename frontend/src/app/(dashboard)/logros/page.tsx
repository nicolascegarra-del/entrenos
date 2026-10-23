"use client";

import { Flame, Trophy } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAchievements, useSetWeeklyGoal } from "@/hooks/use-api";
import {
  achievementIcon,
  daysLeft,
  GROUP_ICON,
  perDayNeeded,
  weeksText,
} from "@/lib/achievements";
import { ApiError } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AchievementsReport } from "@/types/api";

const VISIBLE = 12;

function Bar({ pct, label }: { pct: number; label: string }) {
  return (
    <div
      className="h-2 overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className="h-full rounded-full bg-klyp-accent"
        style={{ width: `${Math.min(100, pct)}%` }}
      />
    </div>
  );
}

function StreakCard({ streak }: { streak: AchievementsReport["streak"] }) {
  const setGoal = useSetWeeklyGoal();
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Flame className="size-5 text-klyp-accent" aria-hidden /> Racha
          semanal
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <p>
            <span className="text-4xl font-bold tabular-nums">
              {streak.current}
            </span>{" "}
            <span className="text-sm text-muted-foreground">
              {streak.current === 1 ? "semana seguida" : "semanas seguidas"}
            </span>
          </p>
          <p className="text-sm text-muted-foreground">
            Mejor racha: {weeksText(streak.best)}
          </p>
        </div>
        <p className="text-sm">
          Esta semana llevas{" "}
          <strong className="tabular-nums">
            {streak.this_week} de {streak.target}
          </strong>{" "}
          entrenos
          {streak.this_week >= streak.target
            ? ": semana cumplida."
            : `: te faltan ${streak.target - streak.this_week} para sumarla.`}
        </p>
        <ol className="grid grid-cols-12 gap-1" aria-label="Últimas 12 semanas">
          {streak.weeks.map((w) => (
            <li
              key={w.start}
              title={`Semana del ${formatDate(`${w.start}T12:00:00`)}: ${w.count} entrenos`}
              className={cn(
                "flex h-9 items-center justify-center rounded-md text-xs tabular-nums",
                w.ok
                  ? "bg-klyp-accent font-semibold text-white"
                  : "border border-dashed text-muted-foreground",
              )}
            >
              <span className="sr-only">
                Semana del {formatDate(`${w.start}T12:00:00`)}:{" "}
                {w.ok ? "cumplida" : "no cumplida"},{" "}
              </span>
              {w.count}
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor="weekly-goal">Entrenos por semana para la racha</label>
          <select
            id="weekly-goal"
            className="h-11 rounded-md border border-input bg-background px-2 md:h-8"
            value={streak.target}
            disabled={setGoal.isPending}
            onChange={(e) =>
              setGoal.mutate(Number(e.target.value), {
                onError: (err) =>
                  toast.error(
                    err instanceof ApiError
                      ? err.message
                      : "No se pudo guardar.",
                  ),
              })
            }
          >
            {[1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </CardContent>
    </Card>
  );
}

function ChallengesCard({
  challenges,
}: {
  challenges: AchievementsReport["challenges"];
}) {
  const today = new Date();
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Retos del mes</CardTitle>
        <p className="text-sm text-muted-foreground">
          Objetivos a tu medida: tu media de los 3 meses anteriores más un 10 %.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-4">
          {challenges.map((c) => {
            const days = daysLeft(c.ends, today);
            const perDay = perDayNeeded(c.current, c.target, days);
            const decimals = c.unit === "km" ? 1 : 0;
            return (
              <li key={c.key} className="space-y-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{c.title}</span>
                  <span className="text-sm tabular-nums">
                    {formatNumber(c.current, decimals)} /{" "}
                    {formatNumber(c.target)} {c.unit}
                  </span>
                </div>
                <Bar
                  pct={(c.current / c.target) * 100}
                  label={`Progreso del reto ${c.title}`}
                />
                <p className="text-xs text-muted-foreground">
                  {c.done
                    ? "¡Reto cumplido!"
                    : `Quedan ${days} ${days === 1 ? "día" : "días"}${
                        c.key === "sessions"
                          ? ` · te faltan ${c.target - c.current}`
                          : perDay != null
                            ? ` · unos ${formatNumber(perDay, decimals)} ${c.unit} al día`
                            : ""
                      }`}
                </p>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

/** Rachas, retos del mes y logros conseguidos. */
export default function LogrosPage() {
  const { data, isPending, isError, refetch } = useAchievements();

  return (
    <section className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="font-heading text-2xl font-bold max-lg:sr-only md:text-3xl">
          Logros
        </h1>
        <p className="text-sm text-muted-foreground">
          Tu constancia, tus retos del mes y los hitos que has ido consiguiendo.
        </p>
      </div>

      {isPending ? (
        <Skeleton className="h-64" />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar tus logros."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <StreakCard streak={data.streak} />
            <ChallengesCard challenges={data.challenges} />
          </div>

          {data.upcoming.length > 0 && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="font-heading text-lg">
                  Próximos hitos
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {data.upcoming.map((u) => {
                    const Icon = GROUP_ICON[u.group];
                    return (
                      <li
                        key={u.key}
                        className="space-y-1 rounded-lg bg-muted/60 p-3"
                      >
                        <p className="flex items-center gap-2 text-sm font-medium">
                          <Icon
                            className="size-4 shrink-0 text-muted-foreground"
                            aria-hidden
                          />
                          {u.title}
                          <span className="ml-auto text-xs font-normal tabular-nums text-muted-foreground">
                            {formatNumber(u.current, u.unit === "km" ? 1 : 0)} /{" "}
                            {formatNumber(u.target, u.target % 1 ? 1 : 0)}{" "}
                            {u.unit}
                          </span>
                        </p>
                        <Bar pct={u.pct} label={`Progreso hacia ${u.title}`} />
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>
          )}

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-baseline gap-2 font-heading text-lg">
                Conseguidos
                <span className="text-sm font-normal text-muted-foreground">
                  {data.milestones.unlocked} de {data.milestones.total} hitos ·{" "}
                  {data.achievements.length} logros en total
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.achievements.length === 0 ? (
                <EmptyState icon={Trophy} title="Aún no hay logros">
                  <p className="text-sm text-muted-foreground">
                    Sincroniza tus entrenos y aparecerán aquí.
                  </p>
                </EmptyState>
              ) : (
                <AchievementList items={data.achievements} />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}

function AchievementList({
  items,
}: {
  items: AchievementsReport["achievements"];
}) {
  const row = (a: AchievementsReport["achievements"][number]) => {
    const Icon = achievementIcon(a.kind, a.key);
    const body = (
      <>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-klyp-accent/15">
          <Icon className="size-4 text-klyp-accent" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{a.title}</span>
          <span className="block text-xs text-muted-foreground">
            {a.description}
          </span>
        </span>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatDate(`${a.achieved_on}T12:00:00`)}
        </span>
      </>
    );
    return (
      <li key={a.key}>
        {a.activity_id ? (
          <Link
            href={`/actividades/${a.activity_id}`}
            className="flex min-h-11 items-center gap-3 rounded-md p-2 hover:bg-muted"
          >
            {body}
          </Link>
        ) : (
          <div className="flex min-h-11 items-center gap-3 p-2">{body}</div>
        )}
      </li>
    );
  };
  return (
    <>
      <ul className="space-y-1">{items.slice(0, VISIBLE).map(row)}</ul>
      {items.length > VISIBLE && (
        <details className="mt-2">
          <summary className="min-h-11 cursor-pointer content-center text-sm font-medium">
            Ver los {items.length - VISIBLE} anteriores
          </summary>
          <ul className="mt-1 space-y-1">{items.slice(VISIBLE).map(row)}</ul>
        </details>
      )}
    </>
  );
}
