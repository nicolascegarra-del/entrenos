"use client";

import { Plus, Swords } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { DuelCard, NewDuelDialog } from "@/components/social/duels";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDuels } from "@/hooks/use-api";
import { duelRecord, recordText } from "@/lib/social";
import type { Duel } from "@/types/api";

function Group({
  title,
  duels,
  kind,
  extra,
}: {
  title: string;
  duels: Duel[];
  kind: "active" | "in" | "out" | "finished";
  extra?: React.ReactNode;
}) {
  if (!duels.length) return null;
  return (
    <section className="space-y-2" aria-label={title}>
      <h2 className="flex flex-wrap items-baseline gap-x-2 font-heading text-lg font-semibold">
        {title}
        <span className="text-sm font-normal text-muted-foreground">
          ({duels.length})
        </span>
        {extra}
      </h2>
      <div className="grid gap-3 md:grid-cols-2">
        {duels.map((d) => (
          <DuelCard key={d.id} duel={d} kind={kind} />
        ))}
      </div>
    </section>
  );
}

/** Duelos 1 contra 1: activos, solicitudes recibidas y enviadas, e historial. */
export default function DuelosPage() {
  const { data, isPending, isError, refetch } = useDuels();
  const [open, setOpen] = useState(false);
  const empty =
    data &&
    !data.active.length &&
    !data.pending_in.length &&
    !data.pending_out.length &&
    !data.finished.length;
  return (
    <section className="space-y-4 md:space-y-6">
      <PageHeader
        title="Duelos"
        subtitle="Reta a un amigo: una semana, dos o un mes"
        hideTitleOnMobile
        actions={
          <Button className="min-h-11 md:min-h-9" onClick={() => setOpen(true)}>
            <Plus aria-hidden /> Nuevo duelo
          </Button>
        }
      />
      {isPending ? (
        <div
          className="grid gap-3 md:grid-cols-2"
          role="status"
          aria-label="Cargando duelos"
        >
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-36 w-full" />
        </div>
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar los duelos."
          onRetry={() => refetch()}
        />
      ) : empty ? (
        <EmptyState icon={Swords} title="Sin duelos todavía">
          <p className="max-w-sm text-sm text-muted-foreground">
            Elige a un amigo, una métrica (km, tiempo, desnivel, días o tu mejor
            5K/10K) y cuánto dura. ¡A ver quién puede más!
          </p>
          <Button className="min-h-11" onClick={() => setOpen(true)}>
            <Plus aria-hidden /> Nuevo duelo
          </Button>
        </EmptyState>
      ) : (
        <>
          <Group title="Te han retado" duels={data.pending_in} kind="in" />
          <Group title="En juego" duels={data.active} kind="active" />
          <Group title="Enviados" duels={data.pending_out} kind="out" />
          <Group
            title="Historial"
            duels={data.finished}
            kind="finished"
            extra={
              <span className="text-sm font-normal text-muted-foreground">
                · {recordText(duelRecord(data.finished))}
              </span>
            }
          />
        </>
      )}
      <NewDuelDialog open={open} onOpenChange={setOpen} />
    </section>
  );
}
