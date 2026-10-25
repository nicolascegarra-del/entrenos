"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  background: "var(--popover)",
  color: "var(--popover-foreground)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
};

/**
 * Perfil de altura de la ruta. Al pasar el dedo o el ratón avisa de la distancia para mover un punto en el
 * mapa (`onHover`), y la quita al salir.
 */
export function ElevationProfile({
  profile,
  onHover,
  height = 140,
}: {
  profile: number[][];
  onHover?: (meters: number | null) => void;
  height?: number;
}) {
  const data = profile.map(([d, alt]) => ({ km: d / 1000, alt }));
  if (data.length < 2)
    return (
      <p className="rounded-md bg-muted/60 p-3 text-sm text-muted-foreground">
        Sin perfil de altura todavía.
      </p>
    );
  const alts = data.map((p) => p.alt);
  const min = Math.min(...alts);
  const max = Math.max(...alts);
  const pad = Math.max(10, (max - min) * 0.15);
  return (
    <figure
      style={{ height }}
      aria-label={`Perfil de altura: de ${Math.round(min)} a ${Math.round(max)} m`}
      onMouseLeave={() => onHover?.(null)}
      onTouchEnd={() => onHover?.(null)}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
          onMouseMove={(state) => {
            const i = state?.activeTooltipIndex;
            if (typeof i === "number" && data[i]) onHover?.(data[i].km * 1000);
          }}
        >
          <defs>
            <linearGradient id="alt-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.5} />
              <stop
                offset="100%"
                stopColor="var(--chart-1)"
                stopOpacity={0.05}
              />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="km"
            type="number"
            domain={[0, "dataMax"]}
            tick={axisTick}
            tickFormatter={(v: number) =>
              `${v.toLocaleString("es-ES", { maximumFractionDigits: 1 })}`
            }
            unit=" km"
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            dataKey="alt"
            width={56}
            domain={[Math.floor(min - pad), Math.ceil(max + pad)]}
            tick={axisTick}
            unit=" m"
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(v) =>
              `Km ${Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 })}`
            }
            formatter={(v) => [`${Math.round(Number(v))} m`, "Altitud"]}
          />
          <Area
            dataKey="alt"
            type="monotone"
            stroke="var(--chart-1)"
            strokeWidth={2}
            fill="url(#alt-fill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  );
}
