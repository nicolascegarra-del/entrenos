"use client";

import {
  CalendarClock,
  Check,
  Gauge,
  NotebookPen,
  Undo2,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useDecideProposal,
  useProposals,
  useSaveCoachMemory,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { CoachEffect } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar.";

type MemoryEffect = Extract<CoachEffect, { tipo: "memoria" }>;
type ProposalEffect = Extract<CoachEffect, { tipo: "propuesta" }>;
type DataEffect = Extract<CoachEffect, { tipo: "perfil" | "umbrales" }>;

/** «Guardado en tu perfil / umbrales» con enlace para revisarlo o corregirlo. */
function DataChip({ effect }: { effect: DataEffect }) {
  const profile = effect.tipo === "perfil";
  const Icon = profile ? UserRound : Gauge;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 text-xs">
      <Icon className="size-4 shrink-0 text-klyp-accent" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="font-medium">
          {profile ? "Guardado en tu perfil" : "Guardado en tus umbrales"}
        </span>{" "}
        <span className="text-muted-foreground">
          {Object.entries(effect.cambios)
            .map(([k, v]) => `${k}: ${v}`)
            .join(" · ")}
        </span>
      </span>
      <Link
        href={profile ? "/ajustes/perfil" : "/progresion/rendimiento"}
        className="inline-flex min-h-11 items-center rounded-md px-2 font-medium text-klyp-accent hover:bg-muted md:min-h-7"
      >
        Revisar
      </Link>
    </div>
  );
}

/** «Guardado en tu ficha» con deshacer (o «Recuperar» si lo olvidó). */
function MemoryChip({ effect }: { effect: MemoryEffect }) {
  const save = useSaveCoachMemory();
  const [undone, setUndone] = useState(false);
  const forgotten = effect.accion === "olvidado";
  const undo = () =>
    save.mutate(
      forgotten
        ? { category: effect.categoria, content: effect.dato }
        : { id: effect.id, remove: true },
      {
        onSuccess: () => setUndone(true),
        onError: (err) => toast.error(errorText(err)),
      },
    );
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 text-xs">
      <NotebookPen className="size-4 shrink-0 text-klyp-accent" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="font-medium">
          {undone
            ? forgotten
              ? "Recuperado en tu ficha"
              : "Quitado de tu ficha"
            : forgotten
              ? "Quitado de tu ficha"
              : effect.accion === "corregido"
                ? "Corregido en tu ficha"
                : "Guardado en tu ficha"}
        </span>{" "}
        <span className="text-muted-foreground">
          ({effect.categoria_nombre}): {effect.dato}
        </span>
      </span>
      {!undone && effect.accion !== "corregido" && (
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 md:min-h-7"
          disabled={save.isPending}
          onClick={undo}
        >
          <Undo2 aria-hidden /> {forgotten ? "Recuperar" : "Deshacer"}
        </Button>
      )}
    </div>
  );
}

/** Propuesta de cambio del plan con aceptar / rechazar (solo mientras siga pendiente). */
function ProposalChip({ effect }: { effect: ProposalEffect }) {
  const { data: pending } = useProposals();
  const decide = useDecideProposal();
  const [done, setDone] = useState<"accepted" | "rejected" | null>(null);
  const still = pending?.some((p) => p.id === effect.id);
  const state = done ?? (pending && !still ? "decided" : null);
  return (
    <div className="space-y-2 rounded-md border bg-background p-2 text-xs">
      <p className="flex items-start gap-2">
        <CalendarClock
          className="mt-0.5 size-4 shrink-0 text-klyp-accent"
          aria-hidden
        />
        <span>
          <span className="font-medium">Propuesta: {effect.resumen}</span>
          <span className="block text-muted-foreground">{effect.motivo}</span>
        </span>
      </p>
      {state ? (
        <p className="text-muted-foreground">
          {state === "accepted"
            ? "Aceptada: tu plan ya está cambiado."
            : state === "rejected"
              ? "Rechazada: el plan sigue igual."
              : "Ya respondiste a esta propuesta."}{" "}
          <Link
            href={`/plan/${effect.sesion_id}`}
            className="text-klyp-accent underline"
          >
            Ver la sesión
          </Link>
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            className="min-h-11 md:min-h-8"
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate(
                { id: effect.id, accept: true },
                {
                  onSuccess: () => {
                    setDone("accepted");
                    toast.success("Plan actualizado.");
                  },
                  onError: (err) => toast.error(errorText(err)),
                },
              )
            }
          >
            <Check aria-hidden /> Aceptar
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 md:min-h-8"
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate(
                { id: effect.id, accept: false },
                {
                  onSuccess: () => setDone("rejected"),
                  onError: (err) => toast.error(errorText(err)),
                },
              )
            }
          >
            <X aria-hidden /> Rechazar
          </Button>
        </div>
      )}
    </div>
  );
}

/** Lo que hizo el entrenador en una respuesta: datos guardados y propuestas del plan. */
export function CoachEffects({ effects }: { effects?: CoachEffect[] | null }) {
  // Los botones (opciones, sugerencias) y «incompleta» los pinta el chat, no van aquí.
  const shown = (effects ?? []).filter(
    (e) =>
      e.tipo === "memoria" ||
      e.tipo === "propuesta" ||
      e.tipo === "perfil" ||
      e.tipo === "umbrales",
  );
  if (!shown.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {shown.map((e, i) =>
        e.tipo === "memoria" ? (
          <MemoryChip key={`m${e.id}-${i}`} effect={e} />
        ) : e.tipo === "propuesta" ? (
          <ProposalChip key={`p${e.id}`} effect={e} />
        ) : e.tipo === "perfil" || e.tipo === "umbrales" ? (
          <DataChip key={`${e.tipo}-${i}`} effect={e} />
        ) : null,
      )}
    </div>
  );
}
