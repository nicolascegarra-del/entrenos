"use client";

import { Download, Laptop, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Platform = "ios" | "android" | "desktop";

interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** Plataforma por el user agent (los iPad con iPadOS se presentan como Mac con pantalla táctil). */
export function detectPlatform(ua: string, touchPoints = 0): Platform {
  if (
    /iphone|ipad|ipod/i.test(ua) ||
    (/macintosh/i.test(ua) && touchPoints > 1)
  )
    return "ios";
  if (/android/i.test(ua)) return "android";
  return "desktop";
}

const TABS: { key: Platform; label: string; icon: typeof Smartphone }[] = [
  { key: "ios", label: "iPhone / iPad", icon: Smartphone },
  { key: "android", label: "Android", icon: Smartphone },
  { key: "desktop", label: "Ordenador", icon: Laptop },
];

const STEPS: Record<Platform, string[]> = {
  ios: [
    "Abre esta página en Safari.",
    "Toca el botón Compartir (el cuadrado con la flecha hacia arriba).",
    "Elige «Añadir a pantalla de inicio» y pulsa «Añadir».",
    "Abre KTrain desde su icono: se ve a pantalla completa, como una app.",
  ],
  android: [
    "Abre esta página en Chrome.",
    "Toca el menú ⋮ (arriba a la derecha).",
    "Elige «Instalar aplicación» o «Añadir a pantalla de inicio».",
    "Abre KTrain desde su icono, como cualquier app.",
  ],
  desktop: [
    "Abre esta página en Chrome o Edge.",
    "Pulsa el icono de instalar que aparece a la derecha de la barra de direcciones.",
    "Confirma con «Instalar»: KTrain se abre en su propia ventana.",
  ],
};

/** «Instálala en tu móvil»: pasos por plataforma y botón directo donde el navegador lo permite. */
export function InstallGuide() {
  const [platform, setPlatform] = useState<Platform>("ios");
  const [installed, setInstalled] = useState(false);
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    setPlatform(detectPlatform(navigator.userAgent, navigator.maxTouchPoints));
    setInstalled(window.matchMedia("(display-mode: standalone)").matches);
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setPrompt(e as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  if (installed) return null;
  return (
    <section
      id="instalar"
      aria-labelledby="instalar-titulo"
      className="mx-auto max-w-3xl px-4 py-12 md:py-16"
    >
      <h2
        id="instalar-titulo"
        className="text-center font-heading text-2xl font-bold md:text-3xl"
      >
        Llévala en tu móvil como una app
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-center text-muted-foreground">
        Sin tiendas ni descargas: se añade a tu pantalla de inicio en un minuto,
        se abre a pantalla completa y te avisa con notificaciones.
      </p>

      <div
        role="tablist"
        aria-label="Tu dispositivo"
        className="mt-6 grid grid-cols-3 gap-1 rounded-lg bg-muted p-1"
      >
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={platform === key}
            onClick={() => setPlatform(key)}
            className={cn(
              "flex min-h-11 items-center justify-center gap-1.5 rounded-md px-2 text-sm font-medium transition-colors",
              platform === key
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            <span className="truncate">{label}</span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        className="mt-4 rounded-lg border bg-card p-4 md:p-6"
      >
        {platform !== "ios" && prompt && (
          <Button
            className="mb-4 h-11 w-full sm:w-auto"
            onClick={async () => {
              await prompt.prompt();
              setPrompt(null);
            }}
          >
            <Download aria-hidden /> Instalar KTrain
          </Button>
        )}
        <ol className="space-y-3">
          {STEPS[platform].map((step, i) => (
            <li key={step} className="flex gap-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-klyp-accent text-sm font-semibold text-white">
                {i + 1}
              </span>
              <span className="pt-0.5">{step}</span>
            </li>
          ))}
        </ol>
        {platform === "ios" && (
          <p className="mt-4 text-sm text-muted-foreground">
            En iPhone y iPad las notificaciones solo funcionan con la app
            añadida a la pantalla de inicio (iOS 16.4 o posterior).
          </p>
        )}
      </div>
    </section>
  );
}
