"use client";

/** Piezas pequeñas de las pantallas de salud (noche y día): cifras, barras de contribuidores. */

import { Tag } from "lucide-react";

import { InfoTerm } from "@/components/glossary/info-term";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { GlossaryKey } from "@/lib/glossary";
import { formatClock, type Contributor } from "@/lib/oura";
import { cn } from "@/lib/utils";
import type { HealthTag } from "@/types/api";

/** Cifra con su etiqueta; si no hay valor no se pinta (`value` null). */
export function Stat({
  label,
  value,
  sub,
  term,
  className,
}: {
  label: string;
  value: string | null;
  sub?: string;
  term?: GlossaryKey;
  className?: string;
}) {
  if (value == null) return null;
  return (
    <div className={cn("rounded-lg bg-muted/60 p-3", className)}>
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {label}
        {term && <InfoTerm term={term} />}
      </p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** Rejilla de cifras: 2 columnas en el móvil, 3 en tablet y 4 en escritorio. */
export function StatGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-4">
      {children}
    </div>
  );
}

/** Puntuación grande 0–100 con su nombre. */
export function Score({
  label,
  score,
  term,
}: {
  label: string;
  score: number | null | undefined;
  term?: GlossaryKey;
}) {
  if (score == null) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-heading text-4xl font-bold tabular-nums">
        {Math.round(score)}
      </span>
      <span className="flex items-center gap-1 text-sm text-muted-foreground">
        {label}
        {term && <InfoTerm term={term} />}
      </span>
    </div>
  );
}

/** Contribuidores de una puntuación como barras 0–100 (un solo tono: no son estados). */
export function ContributorBars({
  items,
  label,
}: {
  items: Contributor[];
  label: string;
}) {
  if (!items.length) return null;
  return (
    <ul className="space-y-2" aria-label={label}>
      {items.map((c) => (
        <li key={c.key} className="space-y-1">
          <div className="flex justify-between gap-2 text-xs">
            <span>{c.label}</span>
            <span className="tabular-nums text-muted-foreground">
              {Math.round(c.value)}
            </span>
          </div>
          <div
            className="h-2 overflow-hidden rounded-full bg-muted"
            role="meter"
            aria-label={c.label}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(c.value)}
          >
            <div
              className="h-full rounded-full bg-klyp-accent"
              style={{ width: `${c.value}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Tarjeta de una sección de la noche o del día. */
export function Block({
  title,
  description,
  children,
  className,
  term,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  term?: GlossaryKey;
}) {
  return (
    <Card className={cn("shadow-sm", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          {title}
          {term && <InfoTerm term={term} />}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  );
}

/** Etiquetas que el usuario puso en la app de Oura. */
export function Tags({ tags }: { tags: HealthTag[] }) {
  if (!tags.length) return null;
  return (
    <Block title="Etiquetas">
      <ul className="space-y-2">
        {tags.map((t, i) => (
          <li
            key={`${t.label}-${i}`}
            className="flex items-start gap-2 text-sm"
          >
            <Tag
              className="mt-0.5 size-4 shrink-0 text-klyp-accent"
              aria-hidden
            />
            <span>
              <span className="font-medium">{t.label}</span>
              {t.start && (
                <span className="text-muted-foreground">
                  {" "}
                  · {formatClock(new Date(t.start).getTime())}
                  {t.end && `–${formatClock(new Date(t.end).getTime())}`}
                </span>
              )}
              {t.comment && (
                <span className="block text-muted-foreground">{t.comment}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Block>
  );
}
