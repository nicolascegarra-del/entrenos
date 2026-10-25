"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { LatLon } from "@/lib/route-edit";

export type MapLayer = "mapa" | "topo";

const LAYERS: Record<
  MapLayer,
  { url: string; attribution: string; maxZoom: number }
> = {
  mapa: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  },
  topo: {
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, <a href="https://opentopomap.org">OpenTopoMap</a>',
    maxZoom: 17,
  },
};

/** Icono de cada punto: verde el inicio, navy el final, blanco los de paso (grandes para el dedo). */
function pointIcon(kind: "start" | "end" | "via", label: string) {
  const bg =
    kind === "start" ? "#0e9f6e" : kind === "end" ? "#051937" : "#ffffff";
  const fg = kind === "via" ? "#051937" : "#ffffff";
  return L.divIcon({
    className: "",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:9999px;background:${bg};color:${fg};border:3px solid #2e6db4;font:600 12px/1 sans-serif;box-shadow:0 1px 4px rgb(0 0 0/.35)">${label}</span>`,
  });
}

function ClickToAdd({ onAdd }: { onAdd: (p: LatLon) => void }) {
  useMapEvents({
    click: (e) => onAdd([e.latlng.lat, e.latlng.lng]),
  });
  return null;
}

/** Encuadra la ruta (o el centro pedido) cuando cambia la clave. */
function Fit({
  points,
  center,
  fitKey,
}: {
  points: LatLon[];
  center: LatLon | null;
  fitKey: number;
}) {
  const map = useMap();
  useEffect(() => {
    if (center) map.flyTo(center, 15, { duration: 0.6 });
    else if (points.length > 1) map.fitBounds(points, { padding: [32, 32] });
    else if (points.length === 1) map.setView(points[0], 15);
    // Solo cuando se pide encuadrar, no en cada cambio de punto.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);
  return null;
}

/** Mapa del editor de rutas. Se importa con next/dynamic (Leaflet necesita `window`). */
export default function RouteEditorMap({
  points,
  geometry,
  hover,
  layer,
  center,
  fitKey,
  loading,
  onAdd,
  onMove,
  onRemove,
}: {
  points: LatLon[];
  geometry: (number | null)[][];
  hover: LatLon | null;
  layer: MapLayer;
  center: LatLon | null;
  fitKey: number;
  loading: boolean;
  onAdd: (p: LatLon) => void;
  onMove: (index: number, p: LatLon) => void;
  onRemove: (index: number) => void;
}) {
  const line = useMemo(
    () => geometry.map((g) => [g[0] as number, g[1] as number] as LatLon),
    [geometry],
  );
  const tiles = LAYERS[layer];
  const loop =
    points.length > 2 &&
    points[0][0] === points[points.length - 1][0] &&
    points[0][1] === points[points.length - 1][1];
  return (
    <MapContainer
      center={points[0] ?? [40.4168, -3.7038]}
      zoom={points.length ? 14 : 6}
      className="size-full"
      attributionControl
    >
      <TileLayer
        key={layer}
        url={tiles.url}
        attribution={tiles.attribution}
        maxZoom={tiles.maxZoom}
      />
      <ClickToAdd onAdd={onAdd} />
      <Fit points={points} center={center} fitKey={fitKey} />
      {line.length > 1 && (
        <Polyline
          positions={line}
          pathOptions={{
            color: "#2e6db4",
            weight: 5,
            opacity: loading ? 0.45 : 0.95,
          }}
        />
      )}
      {points.map((p, i) => {
        // En una circular el último punto es el inicio: no se pinta dos veces.
        if (loop && i === points.length - 1) return null;
        const kind =
          i === 0 ? "start" : i === points.length - 1 ? "end" : "via";
        return (
          <Marker
            key={`${i}-${p[0]}-${p[1]}`}
            position={p}
            draggable
            icon={pointIcon(
              kind,
              kind === "start" ? "S" : kind === "end" ? "F" : String(i),
            )}
            eventHandlers={{
              dragend: (e) => {
                const ll = (e.target as L.Marker).getLatLng();
                onMove(i, [ll.lat, ll.lng]);
              },
              // Clic derecho (PC) o mantener pulsado (móvil): quitar el punto.
              contextmenu: () => onRemove(i),
            }}
            keyboard
            title={
              kind === "start"
                ? "Inicio"
                : kind === "end"
                  ? "Final"
                  : `Punto de paso ${i}`
            }
          />
        );
      })}
      {hover && (
        <CircleMarker
          center={hover}
          radius={8}
          pathOptions={{
            color: "#fff",
            weight: 3,
            fillColor: "#f59e0b",
            fillOpacity: 1,
          }}
        />
      )}
    </MapContainer>
  );
}
