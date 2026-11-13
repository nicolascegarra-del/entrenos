"use client";

import { Loader2, Swords } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/social/segmented";
import { errorText, PersonAvatar } from "@/components/social/person";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateDuel, useDuelAction, useFollowing } from "@/hooks/use-api";
import {
  daysLeft,
  daysLeftText,
  duelDescription,
  duelLeader,
  duelOutcome,
  duelScore,
  duelShare,
  DURATION_LABELS,
  formatMetric,
  METRIC_LABELS,
  OUTCOME_LABELS,
  rivalOf,
  SPORT_LABELS,
  todayIso,
} from "@/lib/social";
import { cn } from "@/lib/utils";
import type {
  Duel,
  DuelDuration,
  DuelMetric,
  PersonRef,
  SocialSport,
} from "@/types/api";

/** Barra comparativa: tu parte (azul) frente a la del rival, con el marcador como texto accesible. */
export function DuelBar({ duel }: { duel: Duel }) {
  const share = Math.round(duelShare(duel) * 100);
  return (
    <div
      role="img"
      aria-label={duelScore(duel)}
      className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
    >
      <div className="h-full bg-klyp-accent" style={{ width: `${share}%` }} />
      <div
        className="h-full bg-amber-500 dark:bg-amber-400"
        style={{ width: `${100 - share}%` }}
      />
    </div>
  );
}

const LEADER_TEXT = {
  me: "Vas ganando",
  them: "Vas perdiendo",
  tie: "Empate",
} as const;

/** Marcador de un duelo: «Tú 23,4 km · Ana 21,0 km», barra y días que quedan. */
export function DuelScoreboard({ duel }: { duel: Duel }) {
  const rival = rivalOf(duel);
  const leader = duelLeader(duel);
  const left = daysLeft(duel.end_date, todayIso());
  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-xs text-muted-foreground">Tú</p>
          <p className="text-lg font-semibold text-klyp-accent tabular-nums">
            {formatMetric(duel.metric, duel.my_value)}
          </p>
        </div>
        <Badge
          variant={leader === "me" ? "default" : "secondary"}
          className="mb-1"
        >
          {LEADER_TEXT[leader]}
        </Badge>
        <div className="text-right">
          <p className="truncate text-xs text-muted-foreground">
            {rival.display_name}
          </p>
          <p className="text-lg font-semibold text-amber-700 tabular-nums dark:text-amber-300">
            {formatMetric(duel.metric, duel.their_value)}
          </p>
        </div>
      </div>
      <DuelBar duel={duel} />
      <p className="text-xs text-muted-foreground">
        {daysLeftText(left)} · {METRIC_LABELS[duel.metric]}
        {duel.sport !== "all" && ` · ${SPORT_LABELS[duel.sport]}`}
      </p>
    </div>
  );
}

/** Tarjeta de un duelo según su estado (activo, recibido, enviado o terminado). */
export function DuelCard({
  duel,
  kind,
}: {
  duel: Duel;
  kind: "active" | "in" | "out" | "finished";
}) {
  const rival = rivalOf(duel);
  const action = useDuelAction();
  const outcome = duelOutcome(duel);
  const run = (a: "accept" | "decline" | "cancel", done: string) =>
    action.mutate(
      { id: duel.id, action: a },
      {
        onSuccess: () => toast.success(done),
        onError: (e) => toast.error(errorText(e)),
      },
    );
  return (
    <Card className="gap-0 py-0 shadow-sm">
      <CardContent className="space-y-3 p-3 md:p-4">
        <div className="flex items-center gap-3">
          <PersonAvatar name={rival.display_name} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">
              {kind === "in"
                ? `${rival.display_name} te reta`
                : `Contra ${rival.display_name}`}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {duelDescription(duel)}
            </p>
          </div>
          {outcome && (
            <Badge
              variant={outcome === "win" ? "default" : "secondary"}
              className={cn(
                outcome === "loss" &&
                  "bg-destructive/15 text-destructive dark:text-red-300",
              )}
            >
              {OUTCOME_LABELS[outcome]}
            </Badge>
          )}
          {duel.status === "declined" && (
            <Badge variant="outline">Rechazado</Badge>
          )}
          {duel.status === "cancelled" && (
            <Badge variant="outline">Cancelado</Badge>
          )}
        </div>
        {kind === "active" && <DuelScoreboard duel={duel} />}
        {kind === "finished" && duel.status === "finished" && (
          <p className="text-sm tabular-nums">{duelScore(duel)}</p>
        )}
        {kind === "in" && (
          <div className="flex flex-wrap gap-2">
            <Button
              className="min-h-11 md:min-h-8"
              size="sm"
              disabled={action.isPending}
              onClick={() =>
                run("accept", "¡Reto aceptado! Que gane el mejor.")
              }
            >
              {action.isPending && <Loader2 className="animate-spin" />}
              Aceptar
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 md:min-h-8"
              disabled={action.isPending}
              onClick={() => run("decline", "Reto rechazado.")}
            >
              Rechazar
            </Button>
          </div>
        )}
        {kind === "out" && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Esperando a que acepte…
            </span>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 md:min-h-8"
              disabled={action.isPending}
              onClick={() => run("cancel", "Reto cancelado.")}
            >
              Cancelar
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const METRICS: DuelMetric[] = [
  "km",
  "time",
  "elevation",
  "days",
  "best_5k",
  "best_10k",
];
const SPORTS: SocialSport[] = ["all", "running", "cycling"];
const DURATIONS: DuelDuration[] = ["1w", "2w", "1m"];

/**
 * Diálogo «Nuevo duelo»: a quién (de la gente que sigues, o la persona ya elegida desde la
 * clasificación o su perfil), métrica, deporte y duración.
 */
export function NewDuelDialog({
  open,
  onOpenChange,
  opponent,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  opponent?: PersonRef;
}) {
  const following = useFollowing(open && !opponent);
  const create = useCreateDuel();
  const [chosen, setChosen] = useState<number | "">("");
  const [metric, setMetric] = useState<DuelMetric>("km");
  const [sport, setSport] = useState<SocialSport>("all");
  const [duration, setDuration] = useState<DuelDuration>("1w");
  const friends = (following.data ?? []).filter(
    (p) => p.follow_status === "accepted" && !p.blocked,
  );
  const opponentId = opponent?.user_id ?? (chosen === "" ? null : chosen);
  const best = metric === "best_5k" || metric === "best_10k";

  const submit = () => {
    if (opponentId == null) return;
    create.mutate(
      {
        opponent_id: opponentId,
        metric,
        // Las mejores marcas de 5K/10K son de carrera.
        sport: best ? "running" : sport,
        duration,
      },
      {
        onSuccess: () => {
          toast.success("Reto enviado. Te avisamos cuando lo acepte.");
          onOpenChange(false);
          setChosen("");
        },
        onError: (e) => toast.error(errorText(e, "No se pudo crear el duelo.")),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Swords className="size-5 text-klyp-accent" aria-hidden />
            {opponent ? `Retar a ${opponent.display_name}` : "Nuevo duelo"}
          </DialogTitle>
          <DialogDescription>
            Un duelo 1 contra 1: gana quien más sume en el periodo (o la mejor
            marca, en 5K y 10K). Empieza cuando lo acepte.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {!opponent && (
            <div className="space-y-1.5">
              <Label htmlFor="duel-friend">Amigo</Label>
              {following.isPending ? (
                <Skeleton className="h-11 w-full" />
              ) : following.isError ? (
                <p className="text-sm text-destructive" role="alert">
                  No se pudo cargar a quién sigues.
                </p>
              ) : friends.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Aún no sigues a nadie. Busca a tus amigos en Personas.
                </p>
              ) : (
                <select
                  id="duel-friend"
                  className="h-11 w-full rounded-md border border-input bg-background px-3 text-base md:h-9 md:text-sm"
                  value={chosen}
                  onChange={(e) =>
                    setChosen(e.target.value ? Number(e.target.value) : "")
                  }
                >
                  <option value="">Elige a quién retar</option>
                  {friends.map((p) => (
                    <option key={p.user_id} value={p.user_id}>
                      {p.display_name} (@{p.handle})
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Métrica</p>
            <div className="flex flex-wrap gap-1">
              <Segmented
                label="Métrica"
                value={metric}
                options={METRICS.slice(0, 4).map((m) => ({
                  value: m,
                  label: METRIC_LABELS[m],
                }))}
                onChange={setMetric}
              />
              <Segmented
                label="Mejor marca"
                value={metric}
                options={METRICS.slice(4).map((m) => ({
                  value: m,
                  label: METRIC_LABELS[m],
                }))}
                onChange={setMetric}
              />
            </div>
          </div>
          {!best && (
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Deporte</p>
              <Segmented
                label="Deporte"
                value={sport}
                options={SPORTS.map((s) => ({
                  value: s,
                  label: SPORT_LABELS[s],
                }))}
                onChange={setSport}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Duración</p>
            <Segmented
              label="Duración"
              value={duration}
              options={DURATIONS.map((d) => ({
                value: d,
                label: DURATION_LABELS[d],
              }))}
              onChange={setDuration}
            />
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            onClick={() => onOpenChange(false)}
          >
            Cancelar
          </Button>
          <Button
            className="min-h-11 md:min-h-9"
            disabled={opponentId == null || create.isPending}
            onClick={submit}
          >
            {create.isPending && <Loader2 className="animate-spin" />}
            Enviar reto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
