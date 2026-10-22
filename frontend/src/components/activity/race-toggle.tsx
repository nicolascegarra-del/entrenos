"use client";

import { Flag, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useSetRace } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { ActivitySummary } from "@/types/api";

/** Marcar una actividad como carrera a tope: solo esas alimentan tu nivel (VDOT) si las hay. */
export function RaceToggle({ activity }: { activity: ActivitySummary }) {
  const setRace = useSetRace(activity.id);
  return (
    <Button
      variant={activity.is_race ? "default" : "outline"}
      size="sm"
      aria-pressed={activity.is_race}
      className="min-h-11 md:min-h-8"
      disabled={setRace.isPending}
      title="Las carreras a tope son las que mejor reflejan tu nivel para previsiones y ritmos"
      onClick={() =>
        setRace.mutate(!activity.is_race, {
          onSuccess: (r) =>
            toast.success(
              r.is_race
                ? "Marcada como carrera: tu nivel y tus ritmos se recalculan con ella."
                : "Ya no cuenta como carrera.",
            ),
          onError: (err) =>
            toast.error(
              err instanceof ApiError ? err.message : "No se pudo guardar.",
            ),
        })
      }
    >
      {setRace.isPending ? (
        <Loader2 className="animate-spin" />
      ) : (
        <Flag aria-hidden />
      )}
      {activity.is_race ? "Carrera a tope" : "Marcar como carrera"}
    </Button>
  );
}
