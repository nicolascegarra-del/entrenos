"use client";

import type { LatLngTuple } from "leaflet";
import { ArrowLeft, GitCompare, Trophy } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { TimeChart } from "@/components/progress/time-chart";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRoute } from "@/hooks/use-api";
import { paceText } from "@/lib/compare";
import {
  formatDate,
  formatDistance,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";

const RouteMap = dynamic(() => import("@/components/activity/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full md:h-80" />,
});

/** Un recorrido: mapa, evolución del ritmo en cada intento y elegir dos para comparar. */
export default function RecorridoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, isPending, isError, refetch } = useRoute(Number(id));
  const [picked, setPicked] = useState<number[]>([]);

  const toggle = (activityId: number) =>
    setPicked((p) =>
      p.includes(activityId)
        ? p.filter((x) => x !== activityId)
        : [...p, activityId].slice(-2),
    );

  return (
    <section className="mx-auto max-w-4xl space-y-4">
      <Link
        href="/recorridos"
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Recorridos
      </Link>
      {isPending ? (
        <Skeleton className="h-96" />
      ) : isError ? (
        <ErrorState
          message="No se encontró el recorrido."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <header>
            <h1 className="font-heading text-2xl font-bold md:text-3xl">
              {data.name}
            </h1>
            <p className="text-sm text-muted-foreground">
              {data.count} veces desde el{" "}
              {formatDate(`${data.first_day}T12:00:00`)} ·{" "}
              {formatDistance(data.distance_m)}
            </p>
          </header>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="font-heading text-lg">
                  Recorrido
                </CardTitle>
              </CardHeader>
              <CardContent>
                <RouteMap points={data.track.map((p) => p as LatLngTuple)} />
              </CardContent>
            </Card>
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="font-heading text-lg">
                  Tu ritmo en cada intento
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  Más arriba = más rápido.
                </p>
              </CardHeader>
              <CardContent>
                <TimeChart
                  height="h-64"
                  reversed
                  data={data.efforts.map((e) => ({
                    t: new Date(`${e.day}T12:00:00`).getTime(),
                    pace: e.pace_s_km,
                  }))}
                  format={(v) => paceText(v)}
                  series={[
                    {
                      key: "pace",
                      label: "Ritmo",
                      color: "var(--chart-1)",
                      kind: "dots",
                    },
                  ]}
                />
              </CardContent>
            </Card>
          </div>

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="font-heading text-lg">Intentos</CardTitle>
              <p className="text-xs text-muted-foreground">
                Marca dos para compararlos km a km.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1">
                {[...data.efforts].reverse().map((e) => {
                  const best = data.best?.activity_id === e.activity_id;
                  const checked = picked.includes(e.activity_id);
                  return (
                    <li
                      key={e.activity_id}
                      className={cn(
                        "flex min-h-11 items-center gap-3 rounded-md px-2",
                        checked && "bg-klyp-accent/10",
                      )}
                    >
                      <input
                        type="checkbox"
                        className="size-4 shrink-0"
                        checked={checked}
                        onChange={() => toggle(e.activity_id)}
                        aria-label={`Elegir el intento del ${formatDate(`${e.day}T12:00:00`)}`}
                      />
                      <Link
                        href={`/actividades/${e.activity_id}`}
                        className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 py-2 text-sm hover:underline"
                      >
                        <span className="w-24 shrink-0">
                          {formatDate(`${e.day}T12:00:00`)}
                        </span>
                        <span className="tabular-nums">
                          {formatDuration(e.duration_s)}
                        </span>
                        <span className="tabular-nums text-muted-foreground">
                          {paceText(e.pace_s_km)} /km
                        </span>
                        {e.avg_hr && (
                          <span className="tabular-nums text-muted-foreground">
                            {formatNumber(e.avg_hr)} ppm
                          </span>
                        )}
                        {best && (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-klyp-accent">
                            <Trophy className="size-3" aria-hidden /> Mejor
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <Button
                className="min-h-11 md:min-h-9"
                disabled={picked.length !== 2}
                onClick={() => {
                  const [x, y] = [...picked].sort(
                    (p, q) =>
                      data.efforts.findIndex((e) => e.activity_id === p) -
                      data.efforts.findIndex((e) => e.activity_id === q),
                  );
                  router.push(`/comparar?a=${x}&b=${y}`);
                }}
              >
                <GitCompare aria-hidden /> Comparar los dos elegidos
              </Button>
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
