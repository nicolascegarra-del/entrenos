"use client";

import { BookOpen, Check, ChevronRight, Compass, Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { useTour } from "@/components/tour/tour-provider";
import { useModules } from "@/hooks/use-api";
import { seenTours, toursFor } from "@/lib/tours";

/** Ayuda: tours guiados (el general y uno por pantalla) y el glosario. */
export default function AyudaPage() {
  const { start } = useTour();
  const [seen, setSeen] = useState<Set<string>>(new Set());

  useEffect(() => {
    try {
      setSeen(seenTours(localStorage));
    } catch {
      // Sin almacenamiento: no se marca ninguno como visto.
    }
  }, []);

  const { data: modules } = useModules();
  const [general, ...screens] = toursFor(modules);
  return (
    <section className="mx-auto max-w-3xl space-y-4 md:space-y-6">
      <PageHeader
        title="Ayuda"
        subtitle="Te enseño la app con bocadillos sobre cada parte de la pantalla."
      />

      <button
        type="button"
        onClick={() => start(general.key)}
        className="flex w-full min-h-11 items-center gap-3 rounded-lg border border-klyp-accent/50 bg-klyp-accent/5 p-4 text-left hover:bg-klyp-accent/10"
      >
        <Compass className="size-6 shrink-0 text-klyp-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block font-heading font-semibold">
            {general.title} · {general.minutes} min
            {seen.has(general.key) && <SeenMark />}
          </span>
          <span className="block text-sm text-muted-foreground">
            {general.summary}
          </span>
        </span>
        <Play className="size-5 shrink-0 text-klyp-accent" aria-hidden />
      </button>

      <div className="space-y-2">
        <h2 className="font-heading text-lg font-semibold">Cada pantalla</h2>
        <p className="text-sm text-muted-foreground">
          También lo tienes en el «?» de la cabecera de cada pantalla.
        </p>
        <ul className="divide-y overflow-hidden rounded-lg border bg-card shadow-sm">
          {screens.map((t) => (
            <li key={t.key}>
              <button
                type="button"
                onClick={() => start(t.key)}
                className="flex w-full min-h-14 items-center gap-3 px-4 py-3 text-left hover:bg-muted/60"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">
                    {t.title}
                    {seen.has(t.key) && <SeenMark />}
                  </span>
                  <span className="block text-sm text-muted-foreground">
                    {t.summary}
                  </span>
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <Link
        href="/glosario"
        className="flex min-h-14 items-center gap-3 rounded-lg border bg-card px-4 py-3 shadow-sm hover:bg-muted/60"
      >
        <BookOpen className="size-5 shrink-0 text-klyp-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">Glosario</span>
          <span className="block text-sm text-muted-foreground">
            Qué significa cada métrica (carga, frescura, VO2max…) y cómo leerla.
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
      </Link>
    </section>
  );
}

function SeenMark() {
  return (
    <span className="ml-2 inline-flex items-center gap-0.5 text-xs font-normal text-muted-foreground">
      <Check className="size-3.5" aria-hidden /> visto
    </span>
  );
}
