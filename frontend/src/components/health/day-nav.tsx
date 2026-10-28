"use client";

import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { formatDayLong, shiftDay } from "@/lib/oura";
import { toIsoDay } from "@/lib/plan";

/**
 * Cabecera de la noche y del día: volver a Salud, día anterior/siguiente (no se pasa de hoy) y
 * enlace a la otra vista del mismo día.
 */
export function DayNav({
  kind,
  day,
  source,
}: {
  kind: "noche" | "dia";
  day: string;
  source?: string | null;
}) {
  const today = toIsoDay(new Date());
  const prev = shiftDay(day, -1);
  const next = shiftDay(day, 1);
  const base = `/progresion/salud/${kind}`;
  const other =
    kind === "noche"
      ? { href: `/progresion/salud/dia/${day}`, label: "Ver el día" }
      : { href: `/progresion/salud/noche/${day}`, label: "Ver la noche" };
  return (
    <header className="space-y-2">
      <Link
        href="/progresion/salud"
        className="-ml-1 inline-flex min-h-11 items-center gap-1 rounded-md px-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Salud
      </Link>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-heading text-xl font-bold md:text-2xl">
            {kind === "noche" ? "Tu noche" : "Tu día"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {kind === "noche"
              ? `Al despertar el ${formatDayLong(day).toLowerCase()}`
              : formatDayLong(day)}
            {source ? ` · datos de ${source}` : ""}
          </p>
        </div>
        <nav className="flex items-center gap-1" aria-label="Cambiar de día">
          <Button
            asChild
            variant="outline"
            size="icon"
            className="size-11 md:size-9"
          >
            <Link href={`${base}/${prev}`} aria-label="Día anterior">
              <ChevronLeft aria-hidden />
            </Link>
          </Button>
          {next <= today ? (
            <Button
              asChild
              variant="outline"
              size="icon"
              className="size-11 md:size-9"
            >
              <Link href={`${base}/${next}`} aria-label="Día siguiente">
                <ChevronRight aria-hidden />
              </Link>
            </Button>
          ) : (
            <Button
              variant="outline"
              size="icon"
              className="size-11 md:size-9"
              disabled
              aria-label="Día siguiente"
            >
              <ChevronRight aria-hidden />
            </Button>
          )}
          <Button asChild variant="ghost" className="min-h-11 md:min-h-9">
            <Link href={other.href}>{other.label}</Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
