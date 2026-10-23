"use client";

import {
  CalendarCheck,
  CalendarClock,
  Check,
  ChevronRight,
  X,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  useAiProviders,
  useCheckin,
  useDecideProposal,
  useProposals,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { PlanProposal } from "@/types/api";

/** Hoy: revisión semanal pendiente y propuestas del entrenador sin responder. */
export function CoachNudges() {
  const { data: ai } = useAiProviders();
  const hasAi = ai?.providers.some((p) => p.configured && p.enabled);
  const { data: checkin } = useCheckin();
  const { data: proposals } = useProposals();
  if (!hasAi) return null;
  const items = [];
  if (checkin?.status === "pending")
    items.push(
      <Link
        key="checkin"
        href="/asistente/semana"
        className="flex min-h-11 items-center gap-3 rounded-lg border p-3 text-sm hover:bg-muted/60"
      >
        <CalendarCheck
          className="size-5 shrink-0 text-klyp-accent"
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">¿Qué tal la semana?</span>
          <span className="text-muted-foreground">
            Un minuto con tu entrenador para preparar la próxima.
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
      </Link>,
    );
  for (const p of proposals ?? [])
    items.push(
      <Link
        key={`p${p.id}`}
        href={`/plan/${p.planned_session_id}`}
        className="flex min-h-11 items-center gap-3 rounded-lg border border-klyp-accent/50 p-3 text-sm hover:bg-muted/60"
      >
        <CalendarClock
          className="size-5 shrink-0 text-klyp-accent"
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">
            Tu entrenador propone un cambio
          </span>
          <span className="line-clamp-2 text-muted-foreground">
            {p.summary}
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
      </Link>,
    );
  return items.length ? <div className="space-y-2">{items}</div> : null;
}

/** Detalle de una sesión del plan: la propuesta pendiente del entrenador, con aceptar / rechazar. */
export function SessionProposal({ planId }: { planId: number }) {
  const { data: proposals } = useProposals();
  const decide = useDecideProposal();
  const p: PlanProposal | undefined = proposals?.find(
    (x) => x.planned_session_id === planId,
  );
  if (!p) return null;
  const act = (accept: boolean) =>
    decide.mutate(
      { id: p.id, accept },
      {
        onSuccess: () =>
          toast.success(accept ? "Plan actualizado." : "Propuesta descartada."),
        onError: (err) =>
          toast.error(
            err instanceof ApiError ? err.message : "No se pudo completar.",
          ),
      },
    );
  const day = typeof p.change.day === "string" ? p.change.day : null;
  return (
    <div className="space-y-2 rounded-lg border border-klyp-accent/50 bg-klyp-accent/5 p-3 text-sm">
      <p className="flex items-start gap-2">
        <CalendarClock
          className="mt-0.5 size-5 shrink-0 text-klyp-accent"
          aria-hidden
        />
        <span>
          <span className="block font-medium">
            Tu entrenador propone: {p.summary}
          </span>
          <span className="block text-muted-foreground">{p.reason}</span>
          {day && (
            <span className="block text-xs text-muted-foreground">
              Nuevo día: {formatDate(day)}
            </span>
          )}
        </span>
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          className="min-h-11 md:min-h-8"
          disabled={decide.isPending}
          onClick={() => act(true)}
        >
          <Check aria-hidden /> Aceptar
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 md:min-h-8"
          disabled={decide.isPending}
          onClick={() => act(false)}
        >
          <X aria-hidden /> Rechazar
        </Button>
      </div>
    </div>
  );
}
