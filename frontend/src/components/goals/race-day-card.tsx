"use client";

import {
  CloudSun,
  Droplets,
  FileUp,
  Loader2,
  Mountain,
  Trash2,
  Wind,
} from "lucide-react";
import { useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

import { INSIGHT_STATUS } from "@/components/progress/insight";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGoalCourse, useRaceDay } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { kmTick } from "@/lib/compare";
import { formatDuration, formatNumber } from "@/lib/format";
import { minutesList, readText, signedPct } from "@/lib/race-day";
import { cn } from "@/lib/utils";
import type { RaceDayPlan } from "@/types/api";

type Plan = Extract<RaceDayPlan, { available: true }>;

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function WeatherBlock({ plan }: { plan: Plan }) {
  const w = plan.weather;
  if (!w)
    return (
      <p className="rounded-lg bg-muted/60 p-3 text-sm text-muted-foreground">
        {plan.weather_error ??
          "Añade el lugar de la carrera (Editar) para tener en cuenta el clima."}
      </p>
    );
  const heat = plan.heat ? INSIGHT_STATUS[plan.heat.status] : null;
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <CloudSun className="size-4 text-klyp-accent" aria-hidden /> {w.label}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat
          label="Temperatura"
          value={w.temp_c != null ? `${formatNumber(w.temp_c, 1)} °C` : "—"}
        />
        <Stat
          label="Punto de rocío"
          value={
            w.dew_point_c != null ? `${formatNumber(w.dew_point_c, 1)} °C` : "—"
          }
        />
        <Stat
          label="Humedad"
          value={
            w.humidity_pct != null ? `${formatNumber(w.humidity_pct)} %` : "—"
          }
        />
        <Stat
          label="Viento"
          value={w.wind_kmh != null ? `${formatNumber(w.wind_kmh)} km/h` : "—"}
        />
      </div>
      {w.rain_prob_pct != null && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Droplets className="size-3.5" aria-hidden /> Probabilidad de lluvia:{" "}
          {w.rain_prob_pct} %
        </p>
      )}
      {plan.heat && heat && (
        <p
          className={cn(
            "flex items-start gap-2 rounded-lg border p-3 text-sm",
            heat.className,
          )}
        >
          <heat.icon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <span className="sr-only">{heat.label}: </span>
            {plan.heat.advice} Efecto en el ritmo:{" "}
            <strong>{signedPct(plan.heat.pct)}</strong>.
          </span>
        </p>
      )}
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <Wind className="size-3" aria-hidden /> Datos de Open-Meteo. El viento
        no se descuenta del ritmo: tenlo en cuenta en los tramos de cara.
      </p>
    </div>
  );
}

function CourseBlock({ plan, goalId }: { plan: Plan; goalId: number }) {
  const course = useGoalCourse(goalId);
  const input = useRef<HTMLInputElement>(null);
  const c = plan.course;
  const upload = async (file: File) => {
    try {
      const gpx = await readText(file);
      course.mutate(
        { gpx, name: file.name },
        {
          onSuccess: () => toast.success("Recorrido cargado."),
          onError: (err) => toast.error(errorText(err)),
        },
      );
    } catch (err) {
      toast.error(errorText(err));
    }
  };
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <Mountain className="size-4 text-klyp-accent" aria-hidden /> Recorrido
        {c && (
          <span className="font-normal text-muted-foreground">
            · +{formatNumber(c.gain_m)} m / −{formatNumber(c.loss_m)} m · efecto{" "}
            {signedPct(plan.elevation_pct)}
          </span>
        )}
      </p>
      {c?.profile && c.profile.length > 1 && (
        <figure className="h-36" aria-label="Perfil de altitud">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={c.profile.map(([d, e]) => ({ d, e }))}
              margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
            >
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="d"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={kmTick}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                stroke="var(--border)"
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                width={40}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => `${formatNumber(v)} m`}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={false}
                tickLine={false}
                tickCount={3}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--popover)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                  color: "var(--popover-foreground)",
                }}
                labelFormatter={(d: number) => kmTick(d)}
                formatter={(v: number) => [`${formatNumber(v)} m`, "Altitud"]}
              />
              <Area
                dataKey="e"
                type="monotone"
                stroke="var(--chart-3)"
                fill="var(--chart-3)"
                fillOpacity={0.2}
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </figure>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={input}
          type="file"
          accept=".gpx,application/gpx+xml"
          className="sr-only"
          aria-label="Fichero GPX del recorrido"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
        <Button
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={course.isPending}
          onClick={() => input.current?.click()}
        >
          {course.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <FileUp aria-hidden />
          )}
          {c?.source === "gpx" ? "Cambiar GPX" : "Subir GPX del recorrido"}
        </Button>
        {c?.source === "gpx" && (
          <Button
            variant="ghost"
            className="min-h-11 text-destructive md:min-h-9"
            disabled={course.isPending}
            onClick={() =>
              course.mutate(null, {
                onError: (err) => toast.error(errorText(err)),
              })
            }
          >
            <Trash2 aria-hidden /> Quitar
          </Button>
        )}
        {!c && (
          <span className="text-xs text-muted-foreground">
            Sin GPX ni desnivel: se supone un recorrido llano.
          </span>
        )}
      </div>
    </div>
  );
}

function PacingTable({ plan }: { plan: Plan }) {
  const [mode, setMode] = useState<"forecast" | "target">("forecast");
  const rows =
    mode === "target" && plan.pacing_target ? plan.pacing_target : plan.pacing;
  const varies = rows.some((r) => Math.abs(r.factor - 1) > 0.005);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">Ritmo por kilómetro</p>
        {plan.pacing_target && (
          <div className="flex gap-1" role="group" aria-label="Plan de ritmos">
            {(["forecast", "target"] as const).map((m) => (
              <Button
                key={m}
                size="sm"
                variant={mode === m ? "default" : "outline"}
                aria-pressed={mode === m}
                className="min-h-11 md:min-h-8"
                onClick={() => setMode(m)}
              >
                {m === "forecast" ? "Previsto" : "Objetivo"}
              </Button>
            ))}
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {varies
          ? "Mismo esfuerzo en todo el recorrido: más lento en las subidas y más rápido en las bajadas."
          : "Ritmo constante (recorrido llano)."}
      </p>
      <div className="max-h-80 overflow-auto rounded-lg border">
        <table className="w-full text-sm tabular-nums">
          <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-1.5 font-medium">Km</th>
              <th className="px-3 py-1.5 font-medium">Ritmo</th>
              <th className="px-3 py-1.5 font-medium">Paso</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.km} className="border-t">
                <td className="px-3 py-1.5">
                  {r.distance_m < 1000
                    ? `${formatNumber(r.km - 1 + r.distance_m / 1000, 1)}`
                    : r.km}
                </td>
                <td className="px-3 py-1.5">
                  {formatDuration(r.pace_s_km)} /km
                  {r.factor > 1.01 && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      ↗
                    </span>
                  )}
                  {r.factor < 0.99 && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      ↘
                    </span>
                  )}
                </td>
                <td className="px-3 py-1.5">{formatDuration(r.cum_s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FuelBlock({ plan }: { plan: Plan }) {
  const f = plan.fueling;
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">Avituallamiento</p>
      <ul className="list-disc space-y-1 pl-5">
        {f.carbs_g_h[1] > 0 && (
          <li>
            Hidratos: {f.carbs_g_h[0]}–{f.carbs_g_h[1]} g por hora.
            {f.gels > 0 &&
              ` ${f.gels === 1 ? "Un gel" : `Unos ${f.gels} geles`} (${minutesList(f.gel_times_min)}); el resto con bebida isotónica.`}
          </li>
        )}
        <li>
          Líquido: {f.fluid_ml_h[0]}–{f.fluid_ml_h[1]} ml por hora, en pequeños
          sorbos.
        </li>
        {f.sodium && <li>Añade sales (sodio): 300–600 mg por hora.</li>}
        <li className="text-muted-foreground">{f.note}</li>
      </ul>
      <p className="text-xs text-muted-foreground">{f.evidence.join(" · ")}</p>
    </div>
  );
}

/** Día de carrera: previsión ajustada por clima y desnivel, ritmos por km y avituallamiento. */
export function RaceDayCard({ goalId }: { goalId: number }) {
  const { data, isPending, isError, refetch } = useRaceDay(goalId);
  return (
    <Card className="shadow-sm lg:col-span-2">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Día de carrera</CardTitle>
        <CardDescription>
          Tu previsión ajustada al clima y al desnivel del recorrido, con el
          ritmo de cada kilómetro.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {isPending ? (
          <Skeleton className="h-48" />
        ) : isError ? (
          <div className="space-y-2 text-sm">
            <p>No se pudo preparar el plan del día de carrera.</p>
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => refetch()}
            >
              Reintentar
            </Button>
          </div>
        ) : !data.available ? (
          <p className="text-sm text-muted-foreground">{data.reason}</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat
                label={
                  data.base_source === "forecast"
                    ? "Previsión en llano y fresco"
                    : "Tu objetivo"
                }
                value={formatDuration(data.base_s)}
              />
              <Stat label="Calor" value={signedPct(data.heat_pct)} />
              <Stat label="Desnivel" value={signedPct(data.elevation_pct)} />
              <Stat
                label="Previsión del día"
                value={formatDuration(data.adjusted_s)}
              />
            </div>
            <WeatherBlock plan={data} />
            <CourseBlock plan={data} goalId={goalId} />
            <PacingTable plan={data} />
            <FuelBlock plan={data} />
            <p className="text-xs text-muted-foreground">
              Ajustes: regla de temperatura + punto de rocío (y Ely et al. 2007)
              para el calor; {data.elevation_evidence.join(" · ")} para el
              desnivel. Son estimaciones: escucha tus sensaciones el día de la
              carrera.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
