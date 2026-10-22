"use client";

import Link from "next/link";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDate, formatDuration, formatNumber } from "@/lib/format";
import type { PaceCurve } from "@/types/api";

/** «1 min», «20 min», «1 h». */
export function durationLabel(seconds: number): string {
  return seconds >= 3600 ? `${seconds / 3600} h` : `${seconds / 60} min`;
}

/**
 * Curva de mejores ritmos: eje X = duración, eje Y = ritmo (invertido: arriba = más rápido).
 * Compara el periodo elegido con el anterior de la misma longitud.
 */
export function PaceCurveChart({
  data,
  periodLabel,
}: {
  data: PaceCurve;
  periodLabel: string;
}) {
  const rows = data.durations.map((d) => ({
    label: durationLabel(d.seconds),
    current: d.best?.pace_s_km ?? null,
    previous: d.previous?.pace_s_km ?? null,
  }));
  const hasPrevious = rows.some((r) => r.previous != null);
  return (
    <div className="space-y-3">
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={rows}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              stroke="var(--border)"
              tickLine={false}
            />
            <YAxis
              width={44}
              reversed
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => formatDuration(v)}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              tickCount={4}
            />
            <Tooltip
              cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--popover-foreground)",
              }}
              formatter={(v: number, name: string) => [
                `${formatDuration(v)} /km`,
                name,
              ]}
            />
            {hasPrevious && (
              <Legend
                verticalAlign="top"
                height={24}
                iconType="plainline"
                wrapperStyle={{ fontSize: 12, color: "var(--foreground)" }}
              />
            )}
            <Line
              dataKey="current"
              name={periodLabel}
              stroke="var(--chart-1)"
              strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }}
              connectNulls
              isAnimationActive={false}
            />
            {hasPrevious && (
              <Line
                dataKey="previous"
                name="Periodo anterior"
                stroke="var(--chart-2)"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }}
                connectNulls
                isAnimationActive={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Vista de tabla (accesible y con enlace a cada marca). */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[22rem] text-sm tabular-nums">
          <caption className="sr-only">Mejores ritmos por duración</caption>
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 pr-2 font-medium">Duración</th>
              <th className="py-1 pr-2 font-medium">{periodLabel}</th>
              <th className="py-1 pr-2 font-medium">Anterior</th>
              <th className="py-1 font-medium">Dónde</th>
            </tr>
          </thead>
          <tbody>
            {data.durations.map((d) => {
              const gain =
                d.best && d.previous
                  ? d.previous.pace_s_km - d.best.pace_s_km
                  : null;
              return (
                <tr key={d.seconds} className="border-t">
                  <td className="py-1.5 pr-2">{durationLabel(d.seconds)}</td>
                  <td className="py-1.5 pr-2 font-medium">
                    {d.best ? `${formatDuration(d.best.pace_s_km)} /km` : "—"}
                    {gain != null && Math.abs(gain) >= 1 && (
                      <span
                        className={
                          gain > 0
                            ? "ml-1 text-xs text-emerald-700 dark:text-emerald-400"
                            : "ml-1 text-xs text-muted-foreground"
                        }
                      >
                        {gain > 0 ? "−" : "+"}
                        {formatDuration(Math.abs(gain))}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 text-muted-foreground">
                    {d.previous
                      ? `${formatDuration(d.previous.pace_s_km)} /km`
                      : "—"}
                  </td>
                  <td className="py-1.5">
                    {d.best ? (
                      <Link
                        href={`/actividades/${d.best.activity_id}`}
                        className="text-klyp-accent hover:underline"
                      >
                        {formatDate(`${d.best.day}T12:00:00`)}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data.critical_speed && (
        <p className="rounded-lg bg-muted/60 p-3 text-sm">
          <strong>Velocidad crítica</strong>:{" "}
          {formatDuration(data.critical_speed.pace_s_km)} /km · reserva
          anaeróbica (D′) {formatNumber(data.critical_speed.d_prime_m)} m. Es el
          ritmo más rápido que puedes mantener «en estado estable» (unos 30–40
          min); por encima gastas tu reserva D′.
        </p>
      )}
    </div>
  );
}
