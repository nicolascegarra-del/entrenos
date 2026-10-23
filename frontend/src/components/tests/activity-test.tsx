"use client";

import { Droplet, FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { TestResult } from "@/components/tests/test-result";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useActivityTest,
  useMarkTest,
  useTestPrefs,
  useTestProtocols,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { protocolsFor } from "@/lib/tests";
import type { ActivitySummary } from "@/types/api";

/** Dentro del menú «⋯» de la actividad: marcarla como test y analizarla. */
export function MarkTest({
  activity,
  onLactate,
}: {
  activity: ActivitySummary;
  /** Abrir el formulario de lactato con las vueltas de la actividad (si hace lactato). */
  onLactate?: () => void;
}) {
  const { data: protocols } = useTestProtocols();
  const { data: prefs } = useTestPrefs();
  const options = protocolsFor(protocols, activity.sport);
  const mark = useMarkTest(activity.id);
  const [protocol, setProtocol] = useState("");
  if (!options.length) return null;
  const chosen = options.find((p) => p.key === protocol);
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={`test-${activity.id}`}
        className="text-xs font-medium text-muted-foreground"
      >
        ¿Fue un test? Sacamos tus valores automáticamente.
      </label>
      <select
        id={`test-${activity.id}`}
        className="h-11 w-full rounded-md border border-input bg-background px-2 text-sm md:h-9"
        value={protocol}
        onChange={(e) => setProtocol(e.target.value)}
      >
        <option value="">Elige el tipo de test…</option>
        {options.map((p) => (
          <option key={p.key} value={p.key}>
            {p.label}
          </option>
        ))}
      </select>
      {chosen && (
        <p className="text-xs text-muted-foreground">
          {chosen.summary}. {chosen.how}
        </p>
      )}
      <Button
        variant="outline"
        className="min-h-11 w-full md:min-h-9"
        disabled={!protocol || mark.isPending}
        onClick={() =>
          mark.mutate(protocol, {
            onSuccess: (t) => {
              setProtocol("");
              if (t.status === "failed")
                toast.error("No se pudo calcular: mira el detalle del test.");
              else toast.success("Test analizado: revísalo y aplícalo.");
              setTimeout(
                () =>
                  document
                    .getElementById("test-de-la-actividad")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" }),
                300,
              );
            },
            onError: (err) =>
              toast.error(
                err instanceof ApiError ? err.message : "No se pudo analizar.",
              ),
          })
        }
      >
        {mark.isPending ? (
          <Loader2 className="animate-spin" />
        ) : (
          <FlaskConical aria-hidden />
        )}
        Analizar como test
      </Button>
      {onLactate && (prefs?.lactate_tests ?? true) && (
        <Button
          variant="ghost"
          className="min-h-11 w-full md:min-h-9"
          onClick={onLactate}
        >
          <Droplet aria-hidden /> Meter lactatos de las vueltas
        </Button>
      )}
    </div>
  );
}

/** Tarjeta del test de esta actividad (solo si se marcó o venía de una sesión de test). */
export function ActivityTestCard({ activityId }: { activityId: number }) {
  const { data: test } = useActivityTest(activityId);
  if (!test) return null;
  return (
    <Card id="test-de-la-actividad" className="scroll-mt-20 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <FlaskConical className="size-5 text-klyp-accent" aria-hidden /> Test
          de rendimiento
        </CardTitle>
      </CardHeader>
      <CardContent>
        <TestResult test={test} />
      </CardContent>
    </Card>
  );
}
