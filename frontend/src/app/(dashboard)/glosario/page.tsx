import { BookOpen } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { GLOSSARY, type GlossaryEntry } from "@/lib/glossary";

export const metadata = { title: "Glosario · APP ENTRENOS" };

/** Todas las métricas de la app explicadas en lenguaje llano. */
export default function GlosarioPage() {
  const entries = Object.entries(GLOSSARY) as [string, GlossaryEntry][];
  return (
    <section className="space-y-4 md:space-y-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 font-heading text-2xl font-bold md:text-3xl">
          <BookOpen className="size-6 text-klyp-accent" aria-hidden />
          Glosario
        </h1>
        <p className="text-sm text-muted-foreground">
          Qué significa cada valor de la app y cómo leerlo. Son orientaciones de
          entrenamiento, no consejo médico.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {entries.map(([key, e]) => (
          <Card key={key} id={key} className="scroll-mt-20 shadow-sm">
            <CardContent className="space-y-1.5">
              <h2 className="font-heading text-base font-semibold">
                {e.name}
                {e.abbr && (
                  <span className="ml-1.5 text-sm font-normal text-muted-foreground">
                    {e.abbr}
                  </span>
                )}
              </h2>
              <p className="text-sm">{e.what}</p>
              <p className="text-sm text-muted-foreground">{e.read}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
