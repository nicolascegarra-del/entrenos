import { BookOpen } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Explanation, PacesExplanation } from "@/types/api";

function Sources({
  sources,
}: {
  sources: { label: string; url: string | null }[];
}) {
  if (!sources.length) return null;
  return (
    <div className="border-t border-border pt-3">
      <p className="mb-1 text-xs font-medium">Fuentes</p>
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
        {sources.map((s) => (
          <li key={s.label}>
            {s.url ? (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2"
              >
                {s.label}
              </a>
            ) : (
              s.label
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** «Por qué esta previsión»: justificación paso a paso con tus datos y sus fuentes. */
export function ForecastExplanation({
  explanation,
}: {
  explanation: Explanation;
}) {
  if (!explanation.points.length) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <BookOpen className="size-5 text-klyp-accent" aria-hidden /> Por qué
          esta previsión
        </CardTitle>
        <CardDescription>{explanation.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ol className="space-y-3">
          {explanation.points.map((p, i) => (
            <li key={p.title} className="flex gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-klyp-accent text-xs font-semibold text-white">
                {i + 1}
              </span>
              <div className="text-sm">
                <p className="font-medium">{p.title}</p>
                <p className="mt-0.5 text-muted-foreground">{p.text}</p>
              </div>
            </li>
          ))}
        </ol>
        <Sources sources={explanation.sources} />
      </CardContent>
    </Card>
  );
}

/** Explicación de los ritmos de Daniels: de dónde salen y para qué sirve cada intensidad. */
export function PacesExplanationBlock({
  explanation,
}: {
  explanation: PacesExplanation;
}) {
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">{explanation.summary}</p>
      <ul className="space-y-2">
        {explanation.zones.map((z) => (
          <li key={z.key}>
            <span className="font-medium">{z.label}</span>{" "}
            <span className="text-xs text-muted-foreground">({z.percent})</span>
            <p className="text-muted-foreground">{z.purpose}</p>
          </li>
        ))}
      </ul>
      <Sources sources={explanation.sources} />
    </div>
  );
}
