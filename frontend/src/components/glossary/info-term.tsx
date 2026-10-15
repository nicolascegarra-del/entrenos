"use client";

import { Info, Sparkles } from "lucide-react";
import Link from "next/link";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { GLOSSARY, type GlossaryKey } from "@/lib/glossary";
import { cn } from "@/lib/utils";

/**
 * Icono ⓘ que explica una métrica en un globo. Se abre con toque o clic (no con
 * hover) para que funcione igual en el móvil.
 */
export function InfoTerm({
  term,
  className,
}: {
  term: GlossaryKey;
  className?: string;
}) {
  const entry = GLOSSARY[term];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Qué es ${entry.name}`}
          className={cn(
            // Área táctil de 44 px alrededor de un icono pequeño.
            "relative inline-flex size-4 shrink-0 items-center justify-center rounded-full align-middle text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none before:absolute before:-inset-3.5 before:content-['']",
            className,
          )}
        >
          <Info className="size-4" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="space-y-2 text-sm" collisionPadding={16}>
        <p className="font-semibold">
          {entry.name}
          {"abbr" in entry && entry.abbr && (
            <span className="ml-1 font-normal text-muted-foreground">
              ({entry.abbr})
            </span>
          )}
        </p>
        <p>{entry.what}</p>
        <p className="text-muted-foreground">{entry.read}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <Link
            href={`/asistente?q=${encodeURIComponent(`Explícame mi ${entry.name.toLowerCase()}: qué valor tengo y qué significa para mí`)}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-klyp-accent hover:underline"
          >
            <Sparkles className="size-3" aria-hidden /> Pregúntale a la IA
          </Link>
          <Link
            href={`/glosario#${term}`}
            className="inline-block text-xs font-medium text-klyp-accent hover:underline"
          >
            Ver el glosario
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
