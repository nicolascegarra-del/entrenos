"use client";

import "leaflet/dist/leaflet.css";

import type { LatLngTuple } from "leaflet";
import { CircleMarker, MapContainer, Polyline, TileLayer } from "react-leaflet";

/** Mapa del recorrido. Se importa con next/dynamic (Leaflet necesita `window`). */
export default function RouteMap({ points }: { points: LatLngTuple[] }) {
  return (
    <MapContainer
      bounds={points}
      boundsOptions={{ padding: [16, 16] }}
      scrollWheelZoom={false}
      className="h-64 w-full rounded-lg md:h-80"
      attributionControl
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={points} pathOptions={{ color: "#2e6db4", weight: 4, opacity: 0.9 }} />
      <CircleMarker center={points[0]} radius={6} pathOptions={{ color: "#fff", fillColor: "#0e9f6e", fillOpacity: 1 }} />
      <CircleMarker
        center={points[points.length - 1]}
        radius={6}
        pathOptions={{ color: "#fff", fillColor: "#051937", fillOpacity: 1 }}
      />
    </MapContainer>
  );
}
