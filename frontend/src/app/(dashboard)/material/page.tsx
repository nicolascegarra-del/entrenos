"use client";

import {
  Archive,
  ArchiveRestore,
  Footprints,
  Loader2,
  Pencil,
  Plus,
  Star,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteGear, useGear, useSaveGear } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import { GEAR_STATUS, gearForm, gearKmLeft, gearUsedPct } from "@/lib/gear";
import { cn } from "@/lib/utils";
import type { Gear, GearInput } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const BAR_CLASS: Record<Gear["status"], string> = {
  ok: "bg-klyp-accent",
  soon: "bg-amber-500",
  replace: "bg-red-600",
  retired: "bg-muted-foreground",
};

function GearForm({ gear, onDone }: { gear?: Gear; onDone: () => void }) {
  const [form, setForm] = useState<GearInput>(gearForm(gear));
  const save = useSaveGear();
  const set = <K extends keyof GearInput>(key: K, value: GearInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <form
      className="grid gap-3 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { id: gear?.id, body: form },
          {
            onSuccess: () => {
              toast.success(
                gear ? "Cambios guardados." : "Zapatillas añadidas.",
              );
              onDone();
            },
            onError: (err) => toast.error(errorText(err)),
          },
        );
      }}
    >
      <div className="space-y-1.5 md:col-span-2">
        <Label htmlFor="gear-name">Nombre</Label>
        <Input
          id="gear-name"
          required
          maxLength={120}
          placeholder="Ej.: Pegasus 41 rojas"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gear-brand">Marca</Label>
        <Input
          id="gear-brand"
          maxLength={80}
          value={form.brand}
          onChange={(e) => set("brand", e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gear-model">Modelo</Label>
        <Input
          id="gear-model"
          maxLength={80}
          value={form.model}
          onChange={(e) => set("model", e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gear-start">Km que ya tenían</Label>
        <Input
          id="gear-start"
          type="number"
          inputMode="decimal"
          min={0}
          max={5000}
          step="0.1"
          value={form.start_km}
          onChange={(e) => set("start_km", Number(e.target.value))}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gear-alert">Avisarme a los (km)</Label>
        <Input
          id="gear-alert"
          type="number"
          inputMode="numeric"
          min={100}
          max={3000}
          value={form.alert_km}
          onChange={(e) => set("alert_km", Number(e.target.value))}
        />
        <p className="text-xs text-muted-foreground">
          La amortiguación suele durar entre 500 y 800 km.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gear-first">Las uso desde</Label>
        <Input
          id="gear-first"
          type="date"
          value={form.first_use ?? ""}
          onChange={(e) => set("first_use", e.target.value || null)}
        />
        <p className="text-xs text-muted-foreground">
          Si son las predeterminadas, se les asignan tus carreras desde ese día.
        </p>
      </div>
      <label className="flex min-h-11 items-center gap-2 text-sm md:self-center">
        <input
          type="checkbox"
          className="size-4"
          checked={form.is_default}
          onChange={(e) => set("is_default", e.target.checked)}
        />
        Predeterminadas para mis carreras nuevas
      </label>
      <div className="flex flex-wrap gap-2 md:col-span-2">
        <Button
          type="submit"
          className="min-h-11 md:min-h-9"
          disabled={save.isPending}
        >
          {save.isPending && <Loader2 className="animate-spin" />}
          Guardar
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="min-h-11 md:min-h-9"
          onClick={onDone}
        >
          Cancelar
        </Button>
      </div>
    </form>
  );
}

function GearItem({ g, onEdit }: { g: Gear; onEdit: () => void }) {
  const save = useSaveGear();
  const remove = useDeleteGear();
  const pct = gearUsedPct(g);
  const left = gearKmLeft(g);
  const update = (patch: Partial<GearInput>, done: string) =>
    save.mutate(
      { id: g.id, body: { ...gearForm(g), ...patch } },
      {
        onSuccess: () => toast.success(done),
        onError: (err) => toast.error(errorText(err)),
      },
    );

  return (
    <li
      className={cn(
        "space-y-2 rounded-lg border p-3",
        g.retired && "opacity-70",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 font-medium break-words">{g.name}</span>
        {g.is_default && (
          <Badge className="gap-1">
            <Star className="size-3" aria-hidden /> Predeterminadas
          </Badge>
        )}
        {g.from_garmin && <Badge variant="outline">Garmin</Badge>}
        <Badge
          variant={g.status === "ok" || g.retired ? "secondary" : "outline"}
          className={cn(
            g.status === "soon" &&
              "border-amber-500 text-amber-700 dark:text-amber-300",
            g.status === "replace" &&
              "border-red-600 text-red-700 dark:text-red-300",
          )}
        >
          {GEAR_STATUS[g.status]}
        </Badge>
      </div>
      {(g.brand || g.model) && (
        <p className="text-xs text-muted-foreground">
          {[g.brand, g.model].filter(Boolean).join(" · ")}
        </p>
      )}
      <div>
        <div className="flex justify-between text-xs tabular-nums">
          <span>
            {formatNumber(g.total_km)} de {formatNumber(g.alert_km)} km
          </span>
          <span className="text-muted-foreground">
            {g.retired
              ? "Retiradas"
              : left >= 0
                ? `quedan ${formatNumber(left)} km`
                : `${formatNumber(-left)} km por encima`}
          </span>
        </div>
        <div
          className="mt-1 h-2 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Vida útil gastada de ${g.name}`}
        >
          <div
            className={cn("h-full", BAR_CLASS[g.status])}
            style={{ width: `${pct}%` }}
          />
        </div>
        {g.first_use && (
          <p className="mt-1 text-xs text-muted-foreground">
            Desde el {formatDate(`${g.first_use}T12:00:00`)}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 md:min-h-8"
          onClick={onEdit}
        >
          <Pencil aria-hidden /> Editar
        </Button>
        {!g.retired && !g.is_default && (
          <Button
            variant="ghost"
            size="sm"
            className="min-h-11 md:min-h-8"
            disabled={save.isPending}
            onClick={() =>
              update({ is_default: true }, "Ahora son tus predeterminadas.")
            }
          >
            <Star aria-hidden /> Predeterminadas
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 md:min-h-8"
          disabled={save.isPending}
          onClick={() =>
            update(
              { retired: !g.retired, is_default: false },
              g.retired ? "Zapatillas reactivadas." : "Zapatillas retiradas.",
            )
          }
        >
          {g.retired ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />}
          {g.retired ? "Reactivar" : "Retirar"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 text-destructive md:min-h-8"
          disabled={remove.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `¿Borrar «${g.name}»? Sus carreras quedarán sin zapatillas.`,
              )
            )
              return;
            remove.mutate(g.id, {
              onSuccess: () => toast.success("Zapatillas borradas."),
              onError: (err) => toast.error(errorText(err)),
            });
          }}
        >
          <Trash2 aria-hidden /> Borrar
        </Button>
      </div>
    </li>
  );
}

/** Material: zapatillas con sus kilómetros, aviso de cambio y predeterminadas. */
export default function MaterialPage() {
  const { data, isPending, isError, refetch } = useGear();
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const active = (data ?? []).filter((g) => !g.retired);
  const retired = (data ?? []).filter((g) => g.retired);

  const list = (items: Gear[]) => (
    <ul className="space-y-3">
      {items.map((g) =>
        editing === g.id ? (
          <li key={g.id} className="rounded-lg border p-3">
            <GearForm gear={g} onDone={() => setEditing(null)} />
          </li>
        ) : (
          <GearItem key={g.id} g={g} onEdit={() => setEditing(g.id)} />
        ),
      )}
    </ul>
  );

  return (
    <section className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="font-heading text-2xl font-bold max-lg:sr-only md:text-3xl">
            Material
          </h1>
          <p className="text-sm text-muted-foreground">
            Lleva la cuenta de los kilómetros de tus zapatillas y te avisamos
            cuando toque cambiarlas.
          </p>
        </div>
        {editing !== "new" && (
          <Button
            className="min-h-11 md:min-h-9"
            onClick={() => setEditing("new")}
          >
            <Plus aria-hidden /> Añadir zapatillas
          </Button>
        )}
      </div>

      {editing === "new" && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Nuevas zapatillas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <GearForm onDone={() => setEditing(null)} />
          </CardContent>
        </Card>
      )}

      {isPending ? (
        <Skeleton className="h-40" />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar tu material."
          onRetry={() => refetch()}
        />
      ) : !data.length ? (
        editing !== "new" && (
          <EmptyState icon={Footprints} title="Aún no tienes zapatillas">
            <p className="max-w-sm text-sm text-muted-foreground">
              Añádelas a mano o, si las tienes en Garmin Connect, se importan
              solas en la próxima sincronización.
            </p>
          </EmptyState>
        )
      ) : (
        <>
          {active.length > 0 && list(active)}
          {retired.length > 0 && (
            <details className="rounded-lg border p-3">
              <summary className="min-h-11 cursor-pointer content-center text-sm font-medium">
                Retiradas ({retired.length})
              </summary>
              <div className="mt-3">{list(retired)}</div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
