"use client";

import type { LatLngTuple } from "leaflet";
import { ArrowLeft } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { CompareCharts } from "@/components/activity/compare-charts";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompare } from "@/hooks/use-api";
import { gapText, paceText, signedGap } from "@/lib/compare";
import {
  formatDate,
  formatDistance,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RouteEffort } from "@/types/api";

const CompareMap = dynamic(() => import("@/components/activity/compare-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full md:h-80" />,
});

function EffortCard({
  e,
  tag,
  color,
}: {
  e: RouteEffort;
  tag: string;
  color: string;
}) {
  return (
    <Link
      href={`/actividades/${e.activity_id}`}
      className="block rounded-lg border p-3 hover:bg-muted/60"
    >
      <p className="flex items-center gap-2 text-sm font-medium">
        <span
          className={cn("inline-block h-1 w-5 rounded-full", color)}
          aria-hidden
        />
        {tag} · {formatDate(`${e.day}T12:00:00`)}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">
        {formatDuration(e.duration_s)}
      </p>
      <p className="text-xs text-muted-foreground tabular-nums">
        {formatDistance(e.distance_m)} · {paceText(e.pace_s_km)} /km
        {e.avg_hr ? ` · ${formatNumber(e.avg_hr)} ppm` : ""}
      </p>
    </Link>
  );
}

function Comparison() {
  const params = useSearchParams();
  const a = Number(params.get("a"));
  const b = Number(params.get("b"));
  const { data, isPending, isError, refetch, error } = useCompare(a, b);

  if (!a || !b || a === b)
    return (
      <p className="text-sm text-muted-foreground">
        Elige dos actividades distintas para compararlas.
      </p>
    );
  if (isPending) return <Skeleton className="h-96" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : "No se pudo comparar."
        }
        onRetry={() => refetch()}
      />
    );

  const labelA = `A (${formatDate(`${data.a.day}T12:00:00`)})`;
  const labelB = `B (${formatDate(`${data.b.day}T12:00:00`)})`;
  const finalGap =
    [...data.points].reverse().find((p) => p.gap_s != null)?.gap_s ?? null;
  const toLatLng = (t: [number, number][]) => t.map((p) => p as LatLngTuple);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <EffortCard e={data.a} tag="A" color="bg-chart-1" />
        <EffortCard e={data.b} tag="B" color="bg-chart-2" />
      </div>
      <p className="rounded-lg bg-muted/60 p-3 text-sm">
        En los {formatDistance(data.distance_m)} comunes, <strong>B</strong> fue{" "}
        <strong>{gapText(finalGap)}</strong> que A (tiempo total, incluidas las
        paradas).
      </p>

      {data.track_a.length > 1 && data.track_b.length > 1 && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Recorridos</CardTitle>
            <p className="text-xs text-muted-foreground">
              A en línea continua y B en discontinua.
            </p>
          </CardHeader>
          <CardContent>
            <CompareMap a={toLatLng(data.track_a)} b={toLatLng(data.track_b)} />
          </CardContent>
        </Card>
      )}

      {data.points.length > 1 && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Kilómetro a kilómetro
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CompareCharts
              points={data.points}
              labelA={labelA}
              labelB={labelB}
            />
          </CardContent>
        </Card>
      )}

      {data.splits.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Parciales</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3 font-medium">Km</th>
                  <th className="py-1 pr-3 font-medium">A</th>
                  <th className="py-1 pr-3 font-medium">B</th>
                  <th className="py-1 font-medium">B − A</th>
                </tr>
              </thead>
              <tbody>
                {data.splits.map((s) => (
                  <tr key={s.km} className="border-t">
                    <td className="py-1.5 pr-3">{s.km}</td>
                    <td className="py-1.5 pr-3">{paceText(s.a)}</td>
                    <td className="py-1.5 pr-3">{paceText(s.b)}</td>
                    <td
                      className={cn(
                        "py-1.5 font-medium",
                        s.diff != null &&
                          s.diff < -0.5 &&
                          "text-emerald-700 dark:text-emerald-400",
                        s.diff != null &&
                          s.diff > 0.5 &&
                          "text-red-700 dark:text-red-400",
                      )}
                    >
                      {signedGap(s.diff)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Comparar dos actividades: mapa superpuesto, diferencia por distancia y parciales. */
export default function CompararPage() {
  return (
    <section className="mx-auto max-w-4xl space-y-4">
      <Link
        href="/recorridos"
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Recorridos
      </Link>
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Comparar actividades
      </h1>
      <Suspense fallback={<Skeleton className="h-96" />}>
        <Comparison />
      </Suspense>
    </section>
  );
}
