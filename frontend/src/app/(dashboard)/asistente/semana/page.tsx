"use client";

import { CalendarCheck, Loader2, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CoachEffects } from "@/components/assistant/effects";
import { Markdown } from "@/components/assistant/markdown";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAiProviders,
  useAnswerCheckin,
  useCheckin,
  useOpenCheckin,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";

const SCALES = [
  { key: "energia", label: "Energía", low: "Agotado", high: "A tope" },
  { key: "sueno", label: "Sueño", low: "Fatal", high: "Genial" },
  {
    key: "estres",
    label: "Estrés (fuera del deporte)",
    low: "Nada",
    high: "Mucho",
  },
  { key: "motivacion", label: "Motivación", low: "Ninguna", high: "Mucha" },
] as const;

const textareaClass =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-base shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:text-sm";

/** Escala de 1 a 5 con botones grandes (para el pulgar). */
function Scale({
  label,
  low,
  high,
  value,
  onChange,
}: {
  label: string;
  low: string;
  high: string;
  value?: number;
  onChange: (v: number) => void;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={value === n}
            onClick={() => onChange(n)}
            className={
              "min-h-11 flex-1 rounded-md border text-sm font-medium tabular-nums transition-colors " +
              (value === n
                ? "border-klyp-accent bg-klyp-accent text-white"
                : "hover:bg-muted")
            }
          >
            {n}
          </button>
        ))}
      </div>
      <p className="flex justify-between text-xs text-muted-foreground">
        <span>{low}</span>
        <span>{high}</span>
      </p>
    </fieldset>
  );
}

/** Asistente → Revisión semanal: un minuto de preguntas y el resumen del entrenador IA. */
export default function SemanaPage() {
  const { data: ai } = useAiProviders();
  const { data: checkin, isPending } = useCheckin();
  const open = useOpenCheckin();
  const answer = useAnswerCheckin();
  const [values, setValues] = useState<Record<string, number | string>>({});
  const hasAi = ai?.providers.some((p) => p.configured && p.enabled);

  // Sin revisión de esta semana: se abre al entrar.
  const thisWeek = (() => {
    const d = new Date();
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  })();
  useEffect(() => {
    if (
      !isPending &&
      hasAi &&
      (!checkin || checkin.week_start < thisWeek) &&
      !open.isPending &&
      !open.data
    )
      open.mutate();
  }, [isPending, hasAi, checkin, thisWeek, open]);

  const submit = () =>
    checkin &&
    answer.mutate(
      { id: checkin.id, answers: values },
      {
        onError: (err) =>
          toast.error(
            err instanceof ApiError ? err.message : "No se pudo enviar.",
          ),
      },
    );

  if (ai && !hasAi)
    return (
      <EmptyState icon={Sparkles} title="Conecta un asistente de IA">
        <p className="max-w-sm text-sm text-muted-foreground">
          La revisión semanal la hace tu entrenador IA: añade tu clave en{" "}
          <Link
            href="/ajustes/asistente"
            className="font-medium text-klyp-accent underline"
          >
            Ajustes
          </Link>
          .
        </p>
      </EmptyState>
    );

  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Revisión semanal"
        subtitle={
          checkin ? `Semana del ${formatDate(checkin.week_start)}` : undefined
        }
      />
      {isPending || !checkin ? (
        <Skeleton className="h-80" />
      ) : checkin.status === "done" ? (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 font-heading text-lg">
              <Sparkles className="size-5 text-klyp-accent" aria-hidden /> Tu
              entrenador
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() =>
                answer.mutate({ id: checkin.id, answers: checkin.answers })
              }
              disabled={answer.isPending}
            >
              <RefreshCw aria-hidden /> Rehacer
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Markdown text={checkin.summary} />
            <CoachEffects effects={checkin.effects} />
            <p className="text-xs text-muted-foreground">
              Puede equivocarse; no es consejo médico. Si algo te duele y no
              mejora, consulta con un fisio o médico.
            </p>
          </CardContent>
        </Card>
      ) : checkin.status === "processing" ? (
        <Card className="shadow-sm">
          <CardContent
            className="flex items-center gap-2 p-6 text-sm"
            role="status"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Tu entrenador está repasando tu semana…
          </CardContent>
        </Card>
      ) : (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-heading text-lg">
              <CalendarCheck className="size-5 text-klyp-accent" aria-hidden />{" "}
              ¿Qué tal la semana?
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              {SCALES.map((s) => (
                <Scale
                  key={s.key}
                  label={s.label}
                  low={s.low}
                  high={s.high}
                  value={values[s.key] as number | undefined}
                  onChange={(v) => setValues((x) => ({ ...x, [s.key]: v }))}
                />
              ))}
              <div className="space-y-1">
                <Label htmlFor="molestias">
                  Molestias o dolores (opcional)
                </Label>
                <textarea
                  id="molestias"
                  rows={2}
                  maxLength={500}
                  className={textareaClass}
                  placeholder="Ej. el gemelo derecho me tira desde el martes"
                  onChange={(e) =>
                    setValues((x) => ({ ...x, molestias: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="comentario">¿Algo más? (opcional)</Label>
                <textarea
                  id="comentario"
                  rows={2}
                  maxLength={500}
                  className={textareaClass}
                  placeholder="Ej. la semana que viene viajo y solo puedo 3 días"
                  onChange={(e) =>
                    setValues((x) => ({ ...x, comentario: e.target.value }))
                  }
                />
              </div>
              {checkin.status === "error" && checkin.error && (
                <p className="text-sm text-destructive">{checkin.error}</p>
              )}
              <Button
                type="submit"
                className="min-h-11 w-full md:w-auto"
                disabled={answer.isPending || !Object.keys(values).length}
              >
                {answer.isPending && <Loader2 className="animate-spin" />}
                Enviar a mi entrenador
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
