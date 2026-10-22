"use client";

import { Loader2, MapPin, Search, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGeocode } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { GeoPlace } from "@/types/api";

export interface PlaceValue {
  name: string;
  lat: number;
  lon: number;
}

/** Texto del lugar elegido: «Cartagena, Región de Murcia, España». */
export const placeLabel = (p: GeoPlace) =>
  [p.name, p.region, p.country].filter(Boolean).join(", ");

/** Buscador del lugar de la carrera (Open-Meteo) para el clima del día. */
export function PlaceSearch({
  value,
  onChange,
}: {
  value: PlaceValue | null;
  onChange: (v: PlaceValue | null) => void;
}) {
  const [q, setQ] = useState("");
  const search = useGeocode();

  if (value)
    return (
      <div className="space-y-1">
        <Label>Lugar (para el clima)</Label>
        <p className="flex min-h-11 items-center gap-2 rounded-md border px-3 text-sm md:min-h-9">
          <MapPin className="size-4 shrink-0 text-klyp-accent" aria-hidden />
          <span className="min-w-0 flex-1 truncate">{value.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-9 shrink-0 md:size-7"
            aria-label="Quitar el lugar"
            onClick={() => onChange(null)}
          >
            <X aria-hidden />
          </Button>
        </p>
      </div>
    );

  const run = () => q.trim().length >= 2 && search.mutate(q.trim());
  return (
    <div className="space-y-1">
      <Label htmlFor="place">Lugar (opcional, para el clima)</Label>
      <div className="flex gap-2">
        <Input
          id="place"
          placeholder="Ciudad de la carrera"
          className="h-11 md:h-9"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              run();
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          className="min-h-11 shrink-0 md:min-h-9"
          disabled={q.trim().length < 2 || search.isPending}
          onClick={run}
          aria-label="Buscar lugar"
        >
          {search.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Search aria-hidden />
          )}
        </Button>
      </div>
      {search.isError && (
        <p className="text-xs text-destructive">
          {search.error instanceof ApiError
            ? search.error.message
            : "No se pudo buscar."}
        </p>
      )}
      {search.data && (
        <ul className="rounded-md border" aria-label="Resultados">
          {search.data.length === 0 && (
            <li className="p-2 text-sm text-muted-foreground">
              No se encontró ningún lugar.
            </li>
          )}
          {search.data.map((p) => (
            <li key={`${p.lat},${p.lon}`}>
              <button
                type="button"
                className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm hover:bg-muted"
                onClick={() => {
                  onChange({ name: placeLabel(p), lat: p.lat, lon: p.lon });
                  search.reset();
                  setQ("");
                }}
              >
                <MapPin
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden
                />
                {placeLabel(p)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
