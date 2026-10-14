"use client";

import { Annoyed, Frown, Laugh, Loader2, Meh, Moon, Smile } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeedback, useSaveFeedback } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDuration, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Escala de esfuerzo percibido (RPE 1–10, escala CR-10 de Borg simplificada). */
const RPE_LABELS: Record<number, string> = {
  1: "Muy muy suave",
  2: "Muy suave",
  3: "Suave",
  4: "Algo exigente",
  5: "Moderado",
  6: "Exigente",
  7: "Duro",
  8: "Muy duro",
  9: "Casi máximo",
  10: "Máximo",
};

const FEELINGS = [
  { value: 1, label: "Fatal", icon: Frown },
  { value: 2, label: "Mal", icon: Annoyed },
  { value: 3, label: "Normal", icon: Meh },
  { value: 4, label: "Bien", icon: Smile },
  { value: 5, label: "Genial", icon: Laugh },
];

/** Sensaciones tras el entreno + contexto del día (sueño, FC en reposo…) para relacionarlos. */
export function FeedbackCard({ activityId }: { activityId: number }) {
  const { data, isPending, isError } = useFeedback(activityId);
  const save = useSaveFeedback(activityId);
  const [rpe, setRpe] = useState<number | null>(null);
  const [feeling, setFeeling] = useState<number | null>(null);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!data) return;
    setRpe(data.rpe);
    setFeeling(data.feeling);
    setNotes(data.notes);
  }, [data]);

  if (isPending) return <Skeleton className="h-56 w-full" />;
  if (isError) return null;

  const dirty =
    rpe !== data.rpe || feeling !== data.feeling || notes !== data.notes;
  const ctx = data.context;
  const context = [
    ctx.sleep_seconds != null &&
      `${formatDuration(ctx.sleep_seconds).replace(/:\d\d$/, "")} h de sueño`,
    ctx.sleep_score != null && `sueño ${formatNumber(ctx.sleep_score)}/100`,
    ctx.resting_hr != null && `FC reposo ${formatNumber(ctx.resting_hr)} ppm`,
    ctx.hrv_last_night != null && `HRV ${formatNumber(ctx.hrv_last_night)} ms`,
    ctx.body_battery_max != null &&
      `Body Battery ${formatNumber(ctx.body_battery_max)}`,
  ].filter(Boolean);

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Sensaciones</CardTitle>
        <CardDescription>
          Tu esfuerzo percibido ayuda a interpretar los datos; si no hubo
          pulsómetro, se usa para calcular la carga.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset>
          <legend className="mb-2 text-sm font-medium">
            Esfuerzo percibido (RPE){" "}
            <span className="font-normal text-muted-foreground">
              {rpe ? `· ${rpe} — ${RPE_LABELS[rpe]}` : "· sin indicar"}
            </span>
          </legend>
          <div
            className="grid grid-cols-5 gap-1 sm:grid-cols-10"
            role="radiogroup"
            aria-label="Esfuerzo percibido"
          >
            {Array.from({ length: 10 }, (_, i) => i + 1).map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={rpe === value}
                aria-label={`${value}: ${RPE_LABELS[value]}`}
                title={RPE_LABELS[value]}
                onClick={() => setRpe(rpe === value ? null : value)}
                className={cn(
                  "min-h-11 rounded-md border text-sm font-semibold tabular-nums transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  rpe === value
                    ? "border-klyp-accent bg-klyp-accent text-white"
                    : "border-border hover:bg-muted/60",
                )}
              >
                {value}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm font-medium">
            ¿Cómo te sentiste?
          </legend>
          <div
            className="grid grid-cols-5 gap-1"
            role="radiogroup"
            aria-label="Sensación general"
          >
            {FEELINGS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={feeling === value}
                onClick={() => setFeeling(feeling === value ? null : value)}
                className={cn(
                  "flex min-h-11 flex-col items-center justify-center gap-0.5 rounded-md border py-1.5 text-xs transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  feeling === value
                    ? "border-klyp-accent bg-klyp-accent/10 font-medium"
                    : "border-border hover:bg-muted/60",
                )}
              >
                <Icon className="size-5" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <label
            htmlFor={`notes-${activityId}`}
            className="mb-2 block text-sm font-medium"
          >
            Notas
          </label>
          <textarea
            id={`notes-${activityId}`}
            rows={2}
            maxLength={2000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Piernas cargadas, calor, buen ritmo…"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          />
        </div>

        {context.length > 0 && (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Moon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            Ese día: {context.join(" · ")}
          </p>
        )}

        <Button
          className="min-h-11 w-full sm:w-auto"
          disabled={!dirty || save.isPending}
          onClick={() =>
            save.mutate(
              { rpe, feeling, notes },
              {
                onSuccess: () => toast.success("Sensaciones guardadas"),
                onError: (err) =>
                  toast.error(
                    err instanceof ApiError
                      ? err.message
                      : "No se pudo guardar.",
                  ),
              },
            )
          }
        >
          {save.isPending && <Loader2 className="animate-spin" aria-hidden />}
          Guardar sensaciones
        </Button>
      </CardContent>
    </Card>
  );
}
