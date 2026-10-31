"use client";

import {
  Activity as ActivityIcon,
  Battery,
  Gauge,
  HeartPulse,
  Mountain,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivityAnalysis } from "@/hooks/use-api";
import { formatDate, formatDuration } from "@/lib/format";
import {
  conditionText,
  efficiencyText,
  intensityText,
} from "@/lib/run-metrics";
import type { ActivityAnalysis } from "@/types/api";

const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--popover-foreground)",
};
// Zonas ordenadas de suave a intensa: un solo tono, de claro a oscuro.
const ZONE_SHADES = [35, 50, 65, 82, 100];
const zoneColor = (i: number) =>
  `color-mix(in oklab, var(--chart-1) ${ZONE_SHADES[i] ?? 100}%, var(--card))`;

const minutes = (s: number) =>
  s >= 3600 ? formatDuration(s) : `${Math.round(s / 60)} min`;

/** Tiempo en cada zona de FC: barras horizontales con minutos y % y la tabla de rangos. */
function HrZonesCard({ data }: { data: ActivityAnalysis["hr_zones"] }) {
  const rows = data.zones.map((z, i) => ({
    ...z,
    label: z.name.split(" ")[0],
    color: zoneColor(i),
  }));
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <HeartPulse className="size-5 text-klyp-accent" aria-hidden /> Zonas
          de FC
        </CardTitle>
        <CardDescription>
          Tiempo en cada zona ({data.source}
          {data.lthr ? `, umbral ${Math.round(data.lthr)} ppm` : ""}).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <figure
          className="h-48"
          aria-label="Tiempo en cada zona de frecuencia cardiaca"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 72, bottom: 0, left: 0 }}
              barCategoryGap={4}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={32}
                tick={axisTick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "var(--muted)" }}
                contentStyle={tooltipStyle}
                formatter={(v: number) => [minutes(v), "Tiempo"]}
                labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""}
              />
              <Bar
                dataKey="seconds"
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              >
                {rows.map((r) => (
                  <Cell key={r.name} fill={r.color} />
                ))}
                <LabelList
                  dataKey="seconds"
                  position="right"
                  content={({ x, y, width, height, index }) => {
                    const r = rows[index as number];
                    return (
                      <text
                        x={Number(x) + Number(width) + 6}
                        y={Number(y) + Number(height) / 2}
                        dominantBaseline="middle"
                        fontSize={11}
                        fill="var(--foreground)"
                      >
                        {minutes(r.seconds)} · {r.pct.toLocaleString("es-ES")} %
                      </text>
                    );
                  }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </figure>
        <table className="w-full text-sm tabular-nums">
          <caption className="sr-only">
            Zonas de FC y tiempo en cada una
          </caption>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t">
                <td className="py-1">
                  <span
                    className="mr-2 inline-block size-2.5 rounded-sm align-middle"
                    style={{ background: r.color }}
                    aria-hidden
                  />
                  {r.name}
                </td>
                <td className="py-1 text-muted-foreground">
                  {r.max ? `${r.min}–${r.max}` : `${r.min}+`} ppm
                </td>
                <td className="py-1 text-right">{minutes(r.seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

/** VO2max de la actividad (del reloj o estimado) y el actual, con su percentil. */
function Vo2maxCard({ data }: { data: ActivityAnalysis["vo2max"] }) {
  const p = data.percentile;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Gauge className="size-5 text-klyp-accent" aria-hidden /> VO2max
        </CardTitle>
        <CardDescription>
          El consumo máximo de oxígeno: tu «motor» aeróbico.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.activity ? (
          <div>
            <p className="font-heading text-4xl font-bold tabular-nums">
              {data.activity.toLocaleString("es-ES", {
                maximumFractionDigits: 1,
              })}
              <span className="ml-1 text-base font-normal text-muted-foreground">
                ml/kg/min
              </span>
            </p>
            <p className="text-sm text-muted-foreground">
              {data.source === "reloj"
                ? "Calculado por tu reloj en esta actividad."
                : "Estimado por la app con tu ritmo y FC de esta carrera (orientativo: mejor en llano y a ritmo constante)."}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Esta actividad no da para estimarlo: hace falta una carrera
            sostenida de al menos 15 min, en llano y con pulso.
          </p>
        )}
        {data.current && (
          <p className="text-sm">
            Tu VO2max actual:{" "}
            <strong className="tabular-nums">
              {data.current.toLocaleString("es-ES", {
                maximumFractionDigits: 1,
              })}
            </strong>
            {data.current_day ? ` (${formatDate(data.current_day)})` : ""}
            {data.current_source === "oura" ? ", según tu anillo Oura" : ""}.
          </p>
        )}
        {p && (
          <p className="text-sm text-muted-foreground">
            Para tu edad ({p.age_group} años) estás{" "}
            {p.bound === "below"
              ? "por debajo del percentil 5"
              : p.bound === "above"
                ? "por encima del percentil 95"
                : `en el percentil ${Math.round(p.percentile)}`}
            {` (la mediana es ${p.median.toLocaleString("es-ES")})`}.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const DRIFT_TEXT: Record<string, string> = {
  bien: "Tu FC se mantuvo estable para el ritmo: buena base aeróbica.",
  alta: "Tu FC subió para el mismo ritmo en la 2.ª mitad: calor, deshidratación o falta de fondo.",
  "muy alta":
    "La FC se disparó en la 2.ª mitad: el ritmo fue alto para tu base aeróbica actual (o hizo mucho calor).",
};

const HR_DRIFT_TEXT: Record<string, string> = {
  bien: "Tu pulso se mantuvo estable de principio a fin.",
  alta: "Tu pulso subió en la 2.ª mitad: normal si apretaste al final; si no, cansancio, calor o poca hidratación.",
  "muy alta":
    "Tu pulso se disparó en la 2.ª mitad: el esfuerzo fue creciendo (o hizo calor, o ibas deshidratado).",
};

function HrTile({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: string | null;
}) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums">
        {value}
        <span className="ml-1 text-xs font-normal text-muted-foreground">
          ppm
        </span>
      </dd>
      {sub && (
        <dd className="text-xs text-muted-foreground tabular-nums">{sub}</dd>
      )}
    </div>
  );
}

/** Pulso de la sesión: FC mín./media/máx. (y % de tu FC máx.), deriva de la FC y TRIMP. */
function HeartRateCard({
  data,
  showDrift,
}: {
  data: NonNullable<ActivityAnalysis["heart_rate"]>;
  showDrift: boolean;
}) {
  const pct = (v: number | null) => (v != null ? `${v} % de tu máx.` : null);
  const drift = showDrift ? data.drift : null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <HeartPulse className="size-5 text-klyp-accent" aria-hidden /> Pulso
          de la sesión
        </CardTitle>
        <CardDescription>
          Calculado con la serie de frecuencia cardiaca.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-3 gap-2">
          <HrTile label="Mínima" value={data.min} />
          <HrTile label="Media" value={data.avg} sub={pct(data.avg_pct_max)} />
          <HrTile label="Máxima" value={data.max} sub={pct(data.max_pct_max)} />
        </dl>
        {drift && (
          <div className="rounded-lg bg-muted/60 p-3">
            <p className="text-sm">
              <span className="font-medium">Deriva de la FC:</span>{" "}
              <span className="font-heading text-lg font-semibold tabular-nums">
                {drift.pct > 0 ? "+" : ""}
                {drift.pct.toLocaleString("es-ES")} %
              </span>{" "}
              <span className="text-muted-foreground tabular-nums">
                ({drift.first_hr} → {drift.second_hr} ppm, {drift.level})
              </span>
            </p>
            <p className="text-xs text-muted-foreground">
              {HR_DRIFT_TEXT[drift.level]}
            </p>
          </div>
        )}
        {data.trimp != null && (
          <p className="text-sm">
            <span className="font-medium">TRIMP:</span>{" "}
            <strong className="tabular-nums">{Math.round(data.trimp)}</strong>{" "}
            <span className="text-muted-foreground">
              (carga por pulso de Banister: minutos ponderados por lo alto que
              va tu FC; un rodaje suave de 1 h ronda 60–90).
            </span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Parciales por km: ritmo (barra más larga = km más rápido) y tiempo acumulado; tabla con FC y cadencia. */
function SplitsCard({ data }: { data: ActivityAnalysis }) {
  const rows = data.splits.map((s) => ({
    ...s,
    label: s.distance_m < 990 ? `${s.km}*` : String(s.km),
    speed: s.distance_m / s.seconds,
  }));
  const best = Math.min(...rows.map((r) => r.pace_s_km));
  const hasCadence = rows.some((r) => r.avg_cadence);
  const drift = data.decoupling;
  const hasGap = rows.some((r) => r.gap_s_km != null);
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <ActivityIcon className="size-5 text-klyp-accent" aria-hidden />{" "}
          Parciales por km
        </CardTitle>
        <CardDescription>
          Barra más larga = km más rápido (resaltado). A la derecha, ritmo del
          km · tiempo acumulado desde la salida.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {drift && (
          <div className="rounded-lg bg-muted/60 p-3">
            <p className="text-sm">
              <span className="font-medium">Deriva cardiaca:</span>{" "}
              <span className="font-heading text-lg font-semibold tabular-nums">
                {drift.pct.toLocaleString("es-ES")} %
              </span>{" "}
              <span className="text-muted-foreground">({drift.level})</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {DRIFT_TEXT[drift.level]} Por debajo del 5 % es lo ideal en
              rodajes largos.
            </p>
          </div>
        )}
        <figure
          style={{ height: Math.max(120, rows.length * 26 + 16) }}
          aria-label="Ritmo de cada kilómetro"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 104, bottom: 0, left: 0 }}
              barCategoryGap={3}
            >
              <CartesianGrid horizontal={false} stroke="var(--border)" />
              <XAxis
                type="number"
                hide
                domain={[(min: number) => min * 0.85, "dataMax"]}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={28}
                tick={axisTick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "var(--muted)" }}
                contentStyle={tooltipStyle}
                labelFormatter={(_, p) => `Km ${p?.[0]?.payload?.km ?? ""}`}
                formatter={(_v, _n, item) => {
                  const r = item.payload as (typeof rows)[number];
                  return [
                    [
                      `${formatDuration(r.pace_s_km)} /km`,
                      `acumulado ${formatDuration(r.elapsed_s)}`,
                      r.avg_hr ? `${r.avg_hr} ppm` : null,
                      r.avg_cadence ? `${r.avg_cadence} pasos/min` : null,
                      `+${r.elevation_gain_m} m`,
                    ]
                      .filter(Boolean)
                      .join(" · "),
                    "Km",
                  ];
                }}
              />
              <Bar
                dataKey="speed"
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              >
                {rows.map((r) => (
                  <Cell
                    key={r.km}
                    fill={
                      r.pace_s_km === best
                        ? "var(--chart-1)"
                        : "color-mix(in oklab, var(--chart-1) 45%, var(--card))"
                    }
                  />
                ))}
                <LabelList
                  dataKey="km"
                  position="right"
                  content={({ x, y, width, height, index }) => {
                    const r = rows[index as number];
                    return (
                      <text
                        x={Number(x) + Number(width) + 6}
                        y={Number(y) + Number(height) / 2}
                        dominantBaseline="middle"
                        fontSize={11}
                        fill="var(--foreground)"
                      >
                        {formatDuration(r.pace_s_km)} ·{" "}
                        {formatDuration(r.elapsed_s)}
                      </text>
                    );
                  }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </figure>
        <details className="text-sm" open>
          <summary className="min-h-11 cursor-pointer content-center font-medium md:min-h-8">
            Desglose por km
          </summary>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full min-w-max text-xs tabular-nums sm:text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 pr-2 font-normal">Km</th>
                  <th className="py-1 pr-2 font-normal">Ritmo</th>
                  {hasGap && (
                    <th className="py-1 pr-2 font-normal">En llano</th>
                  )}
                  <th className="py-1 pr-2 font-normal">Acum.</th>
                  <th className="py-1 pr-2 font-normal">FC</th>
                  {hasCadence && (
                    <th className="py-1 pr-2 font-normal">Cadencia</th>
                  )}
                  <th className="py-1 font-normal">Desn.</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.km} className="border-t">
                    <td className="py-1 pr-2">{r.label}</td>
                    <td className="py-1 pr-2">{formatDuration(r.pace_s_km)}</td>
                    {hasGap && (
                      <td className="py-1 pr-2">
                        {r.gap_s_km ? formatDuration(r.gap_s_km) : "—"}
                      </td>
                    )}
                    <td className="py-1 pr-2">{formatDuration(r.elapsed_s)}</td>
                    <td className="py-1 pr-2">{r.avg_hr ?? "—"}</td>
                    {hasCadence && (
                      <td className="py-1 pr-2">{r.avg_cadence ?? "—"}</td>
                    )}
                    <td className="py-1">+{r.elevation_gain_m} m</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Ritmo en min/km
            {hasGap && " · en llano: el ritmo equivalente sin cuestas"} ·
            acumulado desde la salida · FC en ppm
            {hasCadence && " · cadencia en pasos/min"}.
            {rows.some((r) => r.distance_m < 990) &&
              " * Último tramo, de menos de 1 km."}
          </p>
        </details>
      </CardContent>
    </Card>
  );
}

/** Eficiencia de carrera: metros/min por pulsación frente a tu media y su evolución km a km. */
function EfficiencyCard({
  data,
}: {
  data: NonNullable<ActivityAnalysis["efficiency"]>;
}) {
  const rows = data.by_km.filter((r) => r.value != null);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="size-4" aria-hidden /> Eficiencia de carrera
        </CardTitle>
        <CardDescription>
          Metros por minuto por cada pulsación: más alto, más rápido con el
          mismo esfuerzo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-2xl font-semibold tabular-nums">
          {data.value.toLocaleString("es-ES", { maximumFractionDigits: 2 })}
          <span className="ml-1 text-sm font-normal text-muted-foreground">
            m/min por ppm
          </span>
        </p>
        <p className="text-sm">{efficiencyText(data)}</p>
        {rows.length > 2 && (
          <figure aria-label="Eficiencia por kilómetro" className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ left: 0, right: 8, top: 4 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="km" tick={axisTick} tickLine={false} />
                <YAxis
                  width={40}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  domain={["auto", "auto"]}
                />
                {data.baseline && (
                  <ReferenceLine
                    y={data.baseline}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="4 4"
                    label={{
                      value: "tu media",
                      fontSize: 10,
                      fill: "var(--muted-foreground)",
                      position: "insideTopRight",
                    }}
                  />
                )}
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={(km) => `Km ${km}`}
                  formatter={(v) => [Number(v).toFixed(2), "Eficiencia"]}
                />
                <Line
                  dataKey="value"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </figure>
        )}
      </CardContent>
    </Card>
  );
}

/** Condición de rendimiento: la del reloj (con su curva) o la estimada por KTrain. */
function ConditionCard({
  data,
}: {
  data: NonNullable<ActivityAnalysis["performance_condition"]>;
}) {
  const series = data.series.map(([t, v]) => ({ min: Math.round(t / 60), v }));
  const sign = (v: number) => (v > 0 ? `+${v}` : `${v}`);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gauge className="size-4" aria-hidden /> Condición de rendimiento
        </CardTitle>
        <CardDescription>
          {data.source === "reloj"
            ? "La de tu reloj: cómo rindes hoy frente a tu nivel habitual (−20 a +20)."
            : "Estimada por KTrain con tu eficiencia de los minutos 6–20 frente a tu media (−20 a +20)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-2xl font-semibold tabular-nums">
          {sign(data.initial)}
          {data.final != null && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              al final {sign(data.final)}
            </span>
          )}
        </p>
        <p className="text-sm">{conditionText(data)}</p>
        {series.length > 2 && (
          <figure aria-label="Condición durante la carrera" className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ left: 0, right: 8, top: 4 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="min"
                  tick={axisTick}
                  tickLine={false}
                  unit=" min"
                />
                <YAxis
                  width={32}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  domain={[-20, 20]}
                />
                <ReferenceLine y={0} stroke="var(--muted-foreground)" />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={(m) => `Minuto ${m}`}
                  formatter={(v) => [v, "Condición"]}
                />
                <Line
                  dataKey="v"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </figure>
        )}
      </CardContent>
    </Card>
  );
}

/** Carga de la sesión, intensidad frente al umbral, recuperación orientativa y ritmo en llano. */
function LoadCard({
  load,
  gap,
}: {
  load: NonNullable<ActivityAnalysis["load"]>;
  gap: ActivityAnalysis["gap"];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Battery className="size-4" aria-hidden /> Carga y esfuerzo
        </CardTitle>
        <CardDescription>
          Carga estilo TSS: una hora justo en tu umbral son 100.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Carga</dt>
            <dd className="text-xl font-semibold tabular-nums">
              {Math.round(load.load)}
            </dd>
            {load.watch_load != null && (
              <dd className="text-xs text-muted-foreground">
                Según tu reloj: {Math.round(load.watch_load)}
              </dd>
            )}
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Intensidad</dt>
            <dd className="text-xl font-semibold tabular-nums">
              {load.intensity != null
                ? `${Math.round(load.intensity * 100)} %`
                : "—"}
            </dd>
            <dd className="text-xs text-muted-foreground">
              {intensityText(load.intensity)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              Recuperación orientativa
            </dt>
            <dd className="font-medium">
              {load.recovery_h[0]}–{load.recovery_h[1]} h
            </dd>
          </div>
          {gap?.gap_s_km ? (
            <div>
              <dt className="flex items-center gap-1 text-xs text-muted-foreground">
                <Mountain className="size-3" aria-hidden /> Ritmo en llano
              </dt>
              <dd className="font-medium tabular-nums">
                {formatDuration(gap.gap_s_km)} /km
              </dd>
              <dd className="text-xs text-muted-foreground">
                Real {formatDuration(gap.pace_s_km)} /km
              </dd>
            </div>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}

/** Zonas de FC y VO2max (bajo el mapa) y parciales por km de la actividad. */
export function ActivityAnalysisCards({ activityId }: { activityId: number }) {
  const { data, isPending } = useActivityAnalysis(activityId);
  if (isPending)
    return (
      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    );
  if (!data) return null;
  const hasZones = data.hr_zones.zones.some((z) => z.seconds > 0);
  return (
    <>
      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        {hasZones && <HrZonesCard data={data.hr_zones} />}
        {data.heart_rate && (
          <HeartRateCard
            data={data.heart_rate}
            showDrift={!(data.decoupling && data.splits.length > 1)}
          />
        )}
        <Vo2maxCard data={data.vo2max} />
        {data.efficiency && <EfficiencyCard data={data.efficiency} />}
        {data.performance_condition && (
          <ConditionCard data={data.performance_condition} />
        )}
        {data.load && <LoadCard load={data.load} gap={data.gap ?? null} />}
      </div>
      {data.splits.length > 1 && <SplitsCard data={data} />}
    </>
  );
}
