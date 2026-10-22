"use client";

import "leaflet/dist/leaflet.css";

import type { LatLngTuple } from "leaflet";
import { useEffect, useState } from "react";
import { MapContainer, Polyline, TileLayer } from "react-leaflet";

/** Color de un token CSS (Leaflet necesita el valor, no la variable). */
function useCssColor(name: string, fallback: string) {
  const [color, setColor] = useState(fallback);
  useEffect(() => {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    if (v) setColor(v);
  }, [name]);
  return color;
}

/** Dos recorridos superpuestos (A y B). Se importa con next/dynamic. */
export default function CompareMap({
  a,
  b,
}: {
  a: LatLngTuple[];
  b: LatLngTuple[];
}) {
  const colorA = useCssColor("--chart-1", "#2e6db4");
  const colorB = useCssColor("--chart-2", "#d9480f");
  const all = [...a, ...b];
  return (
    <MapContainer
      bounds={all}
      boundsOptions={{ padding: [16, 16] }}
      scrollWheelZoom={false}
      className="h-64 w-full rounded-lg md:h-80"
      attributionControl
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline
        positions={a}
        pathOptions={{ color: colorA, weight: 5, opacity: 0.85 }}
      />
      <Polyline
        positions={b}
        pathOptions={{
          color: colorB,
          weight: 3,
          opacity: 0.95,
          dashArray: "6 6",
        }}
      />
    </MapContainer>
  );
}
