"use client";

import { CalendarPlus, FlaskConical, Loader2, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { TestResult } from "@/components/tests/test-result";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateManualTest,
  useTestProtocols,
  useTests,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { toIsoDay } from "@/lib/plan";
import { parsePace } from "@/lib/tests";
import type { TestSport } from "@/types/api";

const SPORT_LABEL: Record<TestSport, string> = {
  running: "Carrera",
  cycling: "Ciclismo",
  swimming: "Natación",
};

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-2 text-sm md:h-9";

/** Formulario para meter a mano un resultado conocido (otro test, informe de un club…). */
function ManualForm({ onDone }: { onDone: () => void }) {
  const create = useCreateManualTest();
  const [sport, setSport] = useState<TestSport>("running");
  const [day, setDay] = useState(toIsoDay(new Date()));
  const [lthr, setLthr] = useState("");
  const [pace, setPace] = useState("");
  const [vo2, setVo2] = useState("");
  const [hrMax, setHrMax] = useState("");
  const [notes, setNotes] = useState("");
  const num = (v: string) => (v.trim() ? Number(v.replace(",", ".")) : null);
  const paceS = parsePace(pace);
  return (
    <form
      className="grid gap-3 rounded-lg border p-3 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (Number.isNaN(paceS)) {
          toast.error("Escribe el ritmo como m:ss, por ejemplo 4:05.");
          return;
        }
        create.mutate(
          {
            sport,
            test_date: day,
            lthr: num(lthr),
            threshold_pace_s_km: sport === "running" ? paceS : null,
            vo2max: num(vo2),
            hr_max: num(hrMax),
            notes: notes.trim(),
          },
          {
            onSuccess: () => {
              toast.success("Guardado y aplicado a tus zonas.");
              onDone();
            },
            onError: (err) =>
              toast.error(
                err instanceof ApiError ? err.message : "No se pudo guardar.",
              ),
          },
        );
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="mt-sport">Deporte</Label>
        <select
          id="mt-sport"
          className={selectClass}
          value={sport}
          onChange={(e) => setSport(e.target.value as TestSport)}
        >
          {(["running", "cycling"] as TestSport[]).map((s) => (
            <option key={s} value={s}>
              {SPORT_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="mt-day">Fecha del test</Label>
        <Input
          id="mt-day"
          type="date"
          required
          max={toIsoDay(new Date())}
          className="h-11 md:h-9"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="mt-lthr">FC umbral (ppm)</Label>
        <Input
          id="mt-lthr"
          inputMode="numeric"
          className="h-11 md:h-9"
          value={lthr}
          onChange={(e) => setLthr(e.target.value)}
        />
      </div>
      {sport === "running" && (
        <div className="space-y-1">
          <Label htmlFor="mt-pace">Ritmo umbral (min/km)</Label>
          <Input
            id="mt-pace"
            placeholder="4:05"
            inputMode="numeric"
            className="h-11 md:h-9"
            value={pace}
            onChange={(e) => setPace(e.target.value)}
          />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="mt-vo2">VO2max (ml/kg/min)</Label>
        <Input
          id="mt-vo2"
          inputMode="decimal"
          className="h-11 md:h-9"
          value={vo2}
          onChange={(e) => setVo2(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="mt-hrmax">FC máxima (ppm)</Label>
        <Input
          id="mt-hrmax"
          inputMode="numeric"
          className="h-11 md:h-9"
          value={hrMax}
          onChange={(e) => setHrMax(e.target.value)}
        />
      </div>
      <div className="space-y-1 md:col-span-2">
        <Label htmlFor="mt-notes">Notas (opcional)</Label>
        <Input
          id="mt-notes"
          placeholder="Ej. test en pista con el club"
          maxLength={500}
          className="h-11 md:h-9"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <p className="text-xs text-muted-foreground md:col-span-2">
        Mete solo lo que sepas. Se aplica al momento y manda sobre Garmin y las
        estimaciones durante 8 semanas.
      </p>
      <div className="flex flex-wrap gap-2 md:col-span-2">
        <Button
          type="submit"
          className="min-h-11 md:min-h-9"
          disabled={create.isPending}
        >
          {create.isPending && <Loader2 className="animate-spin" />}
          Guardar y aplicar
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

/** Progreso → Rendimiento: historial de tests, alta manual y planificar el siguiente. */
export function TestsCard() {
  const { data: tests, isPending } = useTests();
  const { data: protocols } = useTestProtocols();
  const [adding, setAdding] = useState(false);
  const [plan, setPlan] = useState("run_30min");
  const detectable = (protocols ?? []).filter((p) => p.detectable);
  return (
    <Card className="shadow-sm lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <FlaskConical className="size-5 text-klyp-accent" aria-hidden /> Tus
          tests
        </CardTitle>
        <CardDescription>
          Un test mide tu umbral, VO2max o FC máxima de verdad. Cuando lo
          confirmas, manda 8 semanas sobre Garmin y las estimaciones. Repítelo
          cada 6-8 semanas para seguir tu evolución.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-0 flex-1 space-y-1">
            <Label htmlFor="plan-test">Planificar un test</Label>
            <select
              id="plan-test"
              className={selectClass}
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            >
              {detectable.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label} · {p.summary}
                </option>
              ))}
            </select>
          </div>
          <Button asChild variant="outline" className="min-h-11 md:min-h-9">
            <Link href={`/plan/nueva?test=${plan}`}>
              <CalendarPlus aria-hidden /> Al plan
            </Link>
          </Button>
          {!adding && (
            <Button
              variant="outline"
              className="min-h-11 md:min-h-9"
              onClick={() => setAdding(true)}
            >
              <Plus aria-hidden /> Resultado a mano
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          ¿Ya lo hiciste? Abre la actividad y, en el menú «⋯», elige «¿Fue un
          test?». Si lo planificas, se analiza solo al sincronizar.
        </p>

        {adding && <ManualForm onDone={() => setAdding(false)} />}

        {isPending ? (
          <Skeleton className="h-32" />
        ) : !tests?.length ? (
          <p className="rounded-lg bg-muted/60 p-3 text-sm">
            Aún no tienes tests. El más sencillo: 30 minutos a tope en llano,
            tras calentar bien.
          </p>
        ) : (
          <ul className="divide-y">
            {tests.map((t) => (
              <li key={t.id} className="py-3 first:pt-0 last:pb-0">
                <TestResult test={t} showActivity />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
