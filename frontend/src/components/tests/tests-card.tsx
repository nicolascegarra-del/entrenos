"use client";

import { CalendarPlus, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  CssForm,
  LactateForm,
  ManualForm,
  selectClass,
} from "@/components/tests/test-forms";
import { TestResult } from "@/components/tests/test-result";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useSaveTestPrefs,
  useTestPrefs,
  useTestProtocols,
  useTests,
} from "@/hooks/use-api";

type AddKind = "" | "manual" | "lab" | "lactate" | "css";

const ADD_OPTIONS: { key: Exclude<AddKind, "">; label: string }[] = [
  { key: "manual", label: "Resultado conocido (FC, ritmo, FTP, VO2max…)" },
  { key: "lab", label: "Informe de laboratorio (VO2max, VT1/VT2)" },
  { key: "lactate", label: "Test de lactato escalonado" },
  { key: "css", label: "Natación: CSS con tus tiempos de 400 y 200" },
];

/** Progreso → Rendimiento: historial de tests, alta manual y planificar el siguiente. */
export function TestsCard() {
  const { data: tests, isPending } = useTests();
  const { data: protocols } = useTestProtocols();
  const { data: prefs } = useTestPrefs();
  const savePrefs = useSaveTestPrefs();
  const lactateOn = prefs?.lactate_tests ?? true;
  const [adding, setAdding] = useState<AddKind>("");
  const [plan, setPlan] = useState("run_30min");
  const detectable = (protocols ?? []).filter((p) => p.detectable);
  const options = ADD_OPTIONS.filter((o) => lactateOn || o.key !== "lactate");
  const done = () => setAdding("");
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
        </div>
        <div className="space-y-1">
          <Label htmlFor="add-test">Añadir un test que ya tienes</Label>
          <select
            id="add-test"
            className={selectClass}
            value={adding}
            onChange={(e) => setAdding(e.target.value as AddKind)}
          >
            <option value="">Elige qué quieres meter…</option>
            {options.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-muted-foreground">
          ¿Ya lo hiciste? Abre la actividad y, en el menú «⋯», elige «¿Fue un
          test?». Si lo planificas, se analiza solo al sincronizar.
        </p>

        {adding === "manual" && <ManualForm onDone={done} />}
        {adding === "lab" && <ManualForm lab onDone={done} />}
        {adding === "lactate" && <LactateForm onDone={done} />}
        {adding === "css" && <CssForm onDone={done} />}

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
        <label className="flex min-h-11 cursor-pointer items-center gap-3 border-t pt-3 text-sm">
          <input
            type="checkbox"
            className="size-5"
            checked={!lactateOn}
            disabled={savePrefs.isPending}
            onChange={(e) =>
              savePrefs.mutate({ lactate_tests: !e.target.checked })
            }
          />
          No hago tests de lactato (oculta el test escalonado)
        </label>
      </CardContent>
    </Card>
  );
}
