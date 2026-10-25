/** Miniatura de la traza en SVG (sin teselas: ligera para la lista de rutas). */
export function RouteThumb({
  preview,
  className,
}: {
  preview: number[][];
  className?: string;
}) {
  if (preview.length < 2) return <div className={className} aria-hidden />;
  const lats = preview.map((p) => p[0]);
  const lons = preview.map((p) => p[1]);
  const [minLat, maxLat] = [Math.min(...lats), Math.max(...lats)];
  const [minLon, maxLon] = [Math.min(...lons), Math.max(...lons)];
  // Corrección de la longitud por la latitud para no deformar la forma.
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const w = (maxLon - minLon) * k || 1e-6;
  const h = maxLat - minLat || 1e-6;
  const scale = 88 / Math.max(w, h);
  const ox = (100 - w * scale) / 2;
  const oy = (100 - h * scale) / 2;
  const d = preview
    .map(
      ([lat, lon], i) =>
        `${i ? "L" : "M"}${(ox + (lon - minLon) * k * scale).toFixed(1)} ${(oy + (maxLat - lat) * scale).toFixed(1)}`,
    )
    .join(" ");
  const [sx, sy] = d.slice(1).split(" ").map(Number);
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden>
      <path
        d={d}
        fill="none"
        stroke="var(--chart-1)"
        strokeWidth={4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={sx} cy={sy} r={5} fill="#0e9f6e" />
    </svg>
  );
}
