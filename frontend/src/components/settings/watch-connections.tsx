"use client";

import { Check, Watch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AppleWatch } from "@/components/settings/apple-watch";
import { GarminCard } from "@/components/settings/garmin-card";
import {
  Coros,
  HealthConnect,
  ImportFiles,
} from "@/components/settings/watch-sources";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppleImport, useGarminStatus, useSources } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import {
  connectedBrands,
  mergeBrands,
  parseBrands,
  WATCH_BRANDS,
  type WatchBrand,
} from "@/lib/watch-brands";

const STORAGE_KEY = "watch-brands";

/** Selección de marcas: la guardada en este navegador más las que ya están conectadas. */
function useChosenBrands() {
  const garmin = useGarminStatus();
  const sources = useSources();
  const apple = useAppleImport();
  const [chosen, setChosen] = useState<WatchBrand[]>([]);
  useEffect(() => {
    try {
      setChosen(parseBrands(localStorage.getItem(STORAGE_KEY)));
    } catch {
      setChosen([]);
    }
  }, []);
  const connected = useMemo(
    () => connectedBrands(garmin.data, sources.data, apple.data),
    [garmin.data, sources.data, apple.data],
  );
  const toggle = (key: WatchBrand) => {
    const next = chosen.includes(key)
      ? chosen.filter((k) => k !== key)
      : [...chosen, key];
    setChosen(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Sin almacenamiento (modo privado): la selección dura lo que la página.
    }
  };
  return {
    selected: mergeBrands(chosen, connected),
    connected,
    toggle,
    sources,
  };
}

function BrandPanel({
  brand,
  sources,
}: {
  brand: WatchBrand;
  sources: ReturnType<typeof useSources>;
}) {
  if (brand === "garmin") return <GarminCard />;
  const info = WATCH_BRANDS.find((b) => b.key === brand)!;
  const body =
    brand === "files" ? (
      <ImportFiles />
    ) : sources.isPending ? (
      <Skeleton className="h-40" />
    ) : sources.isError || !sources.data ? (
      <Button
        variant="outline"
        className="min-h-11"
        onClick={() => sources.refetch()}
      >
        Reintentar
      </Button>
    ) : brand === "apple" ? (
      <AppleWatch data={sources.data} />
    ) : brand === "coros" ? (
      <Coros data={sources.data} />
    ) : (
      <HealthConnect data={sources.data} />
    );
  return (
    <Card id={`reloj-${brand}`} className="scroll-mt-20 shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">{info.label}</CardTitle>
        <CardDescription>{info.how}</CardDescription>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}

/**
 * Elegir tu reloj (o varios) y conectarlo: cada marca muestra solo su forma de traer los entrenos.
 * Se usa en la bienvenida y en Ajustes → Conexiones.
 */
export function WatchConnections() {
  const { selected, connected, toggle, sources } = useChosenBrands();
  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-heading text-lg">
            <Watch className="size-5 text-klyp-accent" aria-hidden /> ¿Qué reloj
            usas?
          </CardTitle>
          <CardDescription>
            Elige uno o varios. Si un entreno llega por dos sitios, solo se
            guarda una vez.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-2">
            {WATCH_BRANDS.map((b) => {
              const on = selected.includes(b.key);
              const linked = connected.includes(b.key);
              return (
                <li key={b.key}>
                  <button
                    type="button"
                    aria-pressed={on}
                    disabled={linked}
                    onClick={() => toggle(b.key)}
                    className={cn(
                      "flex min-h-14 w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-muted/60 disabled:cursor-default disabled:hover:bg-transparent",
                      on && "border-klyp-accent bg-klyp-accent/5",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded border",
                        on && "border-klyp-accent bg-klyp-accent text-white",
                      )}
                      aria-hidden
                    >
                      {on && <Check className="size-3.5" />}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">
                        {b.label}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {linked ? "Conectado" : b.how}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
      {selected.map((brand) => (
        <BrandPanel key={brand} brand={brand} sources={sources} />
      ))}
    </div>
  );
}
