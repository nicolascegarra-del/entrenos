"use client";

import { Check, Watch } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";

import { GarminWorkoutsCard } from "@/components/plan/send-to-watch";
import { AppleWatch } from "@/components/settings/apple-watch";
import { CorosOfficial } from "@/components/settings/coros-official";
import { DeviceCard } from "@/components/settings/device-card";
import { GarminCard } from "@/components/settings/garmin-card";
import { OuraCard } from "@/components/settings/oura-card";
import { SyncSettingsCard } from "@/components/settings/sync-settings-card";
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
import {
  useAppleImport,
  useBrandAccounts,
  useGarminStatus,
  useModules,
  useOuraEnabled,
  useOuraStatus,
  useSources,
} from "@/hooks/use-api";
import { moduleOn } from "@/lib/modules";
import { cn } from "@/lib/utils";
import type { DeviceProvider } from "@/types/api";
import {
  connectedBrands,
  connectedDevices,
  DEVICE_BRANDS,
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
  const ouraOn = useOuraEnabled();
  const oura = useOuraStatus(ouraOn);
  const devices = useBrandAccounts();
  const { data: modules } = useModules();
  const [chosen, setChosen] = useState<WatchBrand[]>([]);
  useEffect(() => {
    let saved: WatchBrand[] = [];
    try {
      saved = parseBrands(localStorage.getItem(STORAGE_KEY));
    } catch {
      saved = [];
    }
    // Vuelta de la web de Oura: su tarjeta tiene que verse para enseñar el aviso.
    if (
      new URLSearchParams(window.location.search).has("oura") &&
      !saved.includes("oura")
    )
      saved = [...saved, "oura"];
    setChosen(saved);
  }, []);
  const connected = useMemo(
    () =>
      connectedBrands(
        garmin.data,
        sources.data,
        apple.data,
        ouraOn ? oura.data : undefined,
        devices.data,
      ),
    [garmin.data, sources.data, apple.data, oura.data, ouraOn, devices.data],
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
  // Con el módulo de una marca apagado (Oura, Suunto, Amazfit, Xiaomi), no se ofrece. Apple Watch ya no se
  // ofrece (Apple no deja leer Salud desde fuera del iPhone): solo lo ve quien ya lo tenía, para gestionarlo.
  const offered = (k: WatchBrand) =>
    k === "oura"
      ? ouraOn
      : k === "apple"
        ? connected.includes("apple")
        : (DEVICE_BRANDS as readonly string[]).includes(k)
          ? moduleOn(modules, k as (typeof DEVICE_BRANDS)[number])
          : true;
  const brands = WATCH_BRANDS.filter((b) => offered(b.key));
  const summary = connectedDevices({
    garmin: garmin.data,
    sources: sources.data,
    oura: ouraOn ? oura.data : undefined,
    devices: devices.data,
  });
  return {
    brands,
    selected: mergeBrands(chosen, connected).filter(offered),
    connected,
    toggle,
    sources,
    summary,
    loaded: !garmin.isPending && !sources.isPending,
  };
}

function BrandPanel({
  brand,
  sources,
}: {
  brand: WatchBrand;
  sources: ReturnType<typeof useSources>;
}) {
  if (brand === "garmin")
    return (
      <>
        <GarminCard />
        <GarminWorkoutsCard />
      </>
    );
  const info = WATCH_BRANDS.find((b) => b.key === brand)!;
  const body =
    brand === "oura" ? (
      <OuraCard />
    ) : (DEVICE_BRANDS as readonly string[]).includes(brand) ? (
      <DeviceCard provider={brand as DeviceProvider} />
    ) : brand === "files" ? (
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
      <div className="space-y-3">
        <Suspense>
          <CorosOfficial data={sources.data} />
        </Suspense>
        {sources.data.coros_official?.status === "ok" && <GarminWorkoutsCard />}
        {/* La conexión antigua (email y contraseña) solo se enseña a quien ya la tenía, para quitarla. */}
        {sources.data.coros && <Coros data={sources.data} />}
      </div>
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
  const { brands, selected, connected, toggle, sources, summary, loaded } =
    useChosenBrands();
  const ring = brands.some((b) => b.key === "oura");
  return (
    <div className="space-y-4">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-heading text-lg">
            <Watch className="size-5 text-klyp-accent" aria-hidden />
            {ring ? "¿Qué reloj o anillo usas?" : "¿Qué reloj usas?"}
          </CardTitle>
          <CardDescription>
            Elige uno o varios. Si un entreno llega por dos sitios, solo se
            guarda una vez.
          </CardDescription>
          {loaded && (
            <p
              className={cn(
                "text-sm font-medium",
                summary.connected.length
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-muted-foreground",
              )}
            >
              {summary.label}
              {summary.broken.length > 0 && (
                <span className="block text-amber-700 dark:text-amber-300">
                  {summary.broken.join(" y ")}: conexión caducada, vuelve a
                  conectarla.
                </span>
              )}
            </p>
          )}
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-2">
            {brands.map((b) => {
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
      {connected.length > 0 && <SyncSettingsCard />}
    </div>
  );
}
