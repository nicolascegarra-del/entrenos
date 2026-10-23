"use client";

import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviewSettings, useSaveReviewSettings } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { ReviewSettings, ReviewSport } from "@/types/api";

export const REVIEW_SPORT_LABEL: Record<ReviewSport, string> = {
  running: "Carrera",
  cycling: "Ciclismo",
  strength: "Fuerza",
  swimming: "Natación",
  other: "Otros deportes",
};

/** Ajustes → Asistente IA: análisis automático de cada entreno al sincronizarlo. */
export function ReviewSettingsCard() {
  const { data, isPending } = useReviewSettings();
  const save = useSaveReviewSettings();
  const update = (
    patch: Partial<Pick<ReviewSettings, "enabled" | "sports" | "daily_max">>,
  ) => {
    if (!data) return;
    save.mutate(
      {
        enabled: data.enabled,
        sports: data.sports,
        daily_max: data.daily_max,
        ...patch,
      },
      {
        onError: (err) =>
          toast.error(
            err instanceof ApiError ? err.message : "No se pudo guardar.",
          ),
      },
    );
  };
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Sparkles className="size-5 text-klyp-accent" aria-hidden /> Análisis
          de cada entreno
        </CardTitle>
        <CardDescription>
          Al sincronizar un entreno, tu asistente escribe cómo ha ido, qué te
          aporta, qué mejorar y qué te toca los próximos días. Lo ves en la
          actividad y te avisa al móvil si tienes las notificaciones activadas.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending || !data ? (
          <Skeleton className="h-32" />
        ) : (
          <fieldset className="space-y-4" disabled={save.isPending}>
            {!data.has_ai && (
              <p className="rounded-lg bg-muted/60 p-3 text-sm">
                Primero configura un asistente (ChatGPT, Gemini o Claude) en la
                tarjeta de arriba.
              </p>
            )}
            <label className="flex min-h-11 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                className="size-5"
                checked={data.enabled}
                onChange={(e) => update({ enabled: e.target.checked })}
              />
              <span className="text-sm font-medium">
                Analizar mis entrenos automáticamente
              </span>
            </label>
            <div className="space-y-1">
              <p className="text-sm font-medium">Deportes</p>
              <div className="flex flex-wrap gap-2">
                {(Object.keys(REVIEW_SPORT_LABEL) as ReviewSport[]).map((s) => {
                  const on = data.sports.includes(s);
                  return (
                    <label
                      key={s}
                      className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border px-3 text-sm has-[:checked]:border-klyp-accent"
                    >
                      <input
                        type="checkbox"
                        className="size-4"
                        checked={on}
                        disabled={!data.enabled}
                        onChange={() =>
                          update({
                            sports: on
                              ? data.sports.filter((x) => x !== s)
                              : [...data.sports, s],
                          })
                        }
                      />
                      {REVIEW_SPORT_LABEL[s]}
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <label htmlFor="review-max">Máximo al día</label>
              <select
                id="review-max"
                className="h-11 rounded-md border border-input bg-background px-2 md:h-8"
                value={data.daily_max}
                disabled={!data.enabled}
                onChange={(e) => update({ daily_max: Number(e.target.value) })}
              >
                {[1, 2, 3, 5, 10].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted-foreground">
                Hoy: {data.used_today}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Solo entrenos de las últimas 48 h y de al menos 10 minutos (al
              cargar un histórico no se analiza cada uno). Cada análisis
              consulta tus datos con tu clave: con modelos económicos (Haiku,
              Flash, mini) cuesta céntimos. Nunca se envían coordenadas GPS.
            </p>
          </fieldset>
        )}
      </CardContent>
    </Card>
  );
}
