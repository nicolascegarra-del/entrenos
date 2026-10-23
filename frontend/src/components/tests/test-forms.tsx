"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateLactateTest, useCreateManualTest } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { toIsoDay } from "@/lib/plan";
import { parsePace, parseTime } from "@/lib/tests";
import type { Lap, ManualTestInput, TestSport } from "@/types/api";

export const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-2 text-sm md:h-9";

const SPORT_LABEL: Record<TestSport, string> = {
  running: "Carrera",
  cycling: "Ciclismo",
  swimming: "Natación",
};

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo guardar.";

const num = (v: string) => (v.trim() ? Number(v.replace(",", ".")) : null);

/** Campo de texto corto con su etiqueta. */
function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  mode = "numeric",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mode?: "numeric" | "decimal" | "text";
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode={mode}
        placeholder={placeholder}
        className="h-11 md:h-9"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function SportAndDate({
  idPrefix,
  sport,
  setSport,
  day,
  setDay,
  sports,
}: {
  idPrefix: string;
  sport: TestSport;
  setSport: (s: TestSport) => void;
  day: string;
  setDay: (d: string) => void;
  sports: TestSport[];
}) {
  return (
    <>
      {sports.length > 1 && (
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-sport`}>Deporte</Label>
          <select
            id={`${idPrefix}-sport`}
            className={selectClass}
            value={sport}
            onChange={(e) => setSport(e.target.value as TestSport)}
          >
            {sports.map((s) => (
              <option key={s} value={s}>
                {SPORT_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-day`}>Fecha del test</Label>
        <Input
          id={`${idPrefix}-day`}
          type="date"
          required
          max={toIsoDay(new Date())}
          className="h-11 md:h-9"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>
    </>
  );
}

function Actions({
  pending,
  onCancel,
}: {
  pending: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 md:col-span-2">
      <Button type="submit" className="min-h-11 md:min-h-9" disabled={pending}>
        {pending && <Loader2 className="animate-spin" />}
        Guardar y aplicar
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="min-h-11 md:min-h-9"
        onClick={onCancel}
      >
        Cancelar
      </Button>
    </div>
  );
}

/**
 * Resultado conocido (`manual`) o informe de laboratorio (`lab`): se guarda confirmado y se aplica.
 * En el informe, el segundo umbral (VT2/LT2) da la FC y el ritmo umbral o el FTP.
 */
export function ManualForm({
  lab = false,
  onDone,
}: {
  lab?: boolean;
  onDone: () => void;
}) {
  const create = useCreateManualTest();
  const [sport, setSport] = useState<TestSport>("running");
  const [day, setDay] = useState(toIsoDay(new Date()));
  const [f, setF] = useState<Record<string, string>>({});
  const set = (key: string) => (v: string) => setF((x) => ({ ...x, [key]: v }));
  const running = sport === "running";
  const cycling = sport === "cycling";
  const id = lab ? "lab" : "mt";

  const submit = () => {
    const paces = ["pace", "vt1_pace", "vt2_pace"].map((k) =>
      parsePace(f[k] ?? ""),
    );
    if (paces.some((p) => Number.isNaN(p))) {
      toast.error("Escribe los ritmos como m:ss, por ejemplo 4:05.");
      return;
    }
    const body: ManualTestInput = lab
      ? {
          protocol: "lab",
          sport,
          test_date: day,
          vo2max: num(f.vo2max ?? ""),
          hr_max: num(f.hr_max ?? ""),
          vt1_hr: num(f.vt1_hr ?? ""),
          vt2_hr: num(f.vt2_hr ?? ""),
          vt1_pace_s_km: running ? paces[1] : null,
          vt2_pace_s_km: running ? paces[2] : null,
          vt1_power: cycling ? num(f.vt1_power ?? "") : null,
          vt2_power: cycling ? num(f.vt2_power ?? "") : null,
          notes: (f.notes ?? "").trim(),
        }
      : {
          protocol: "manual",
          sport,
          test_date: day,
          lthr: num(f.lthr ?? ""),
          threshold_pace_s_km: running ? paces[0] : null,
          ftp: cycling ? num(f.ftp ?? "") : null,
          vo2max: num(f.vo2max ?? ""),
          hr_max: num(f.hr_max ?? ""),
          notes: (f.notes ?? "").trim(),
        };
    create.mutate(body, {
      onSuccess: () => {
        toast.success("Guardado y aplicado a tus zonas.");
        onDone();
      },
      onError: (err) => toast.error(errorText(err)),
    });
  };

  return (
    <form
      className="grid gap-3 rounded-lg border p-3 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <SportAndDate
        idPrefix={id}
        sport={sport}
        setSport={setSport}
        day={day}
        setDay={setDay}
        sports={["running", "cycling"]}
      />
      {lab ? (
        <>
          <Field
            id="lab-vo2"
            label="VO2max (ml/kg/min)"
            mode="decimal"
            value={f.vo2max ?? ""}
            onChange={set("vo2max")}
          />
          <Field
            id="lab-hrmax"
            label="FC máxima (ppm)"
            value={f.hr_max ?? ""}
            onChange={set("hr_max")}
          />
          <Field
            id="lab-vt1hr"
            label="Primer umbral (VT1/LT1): FC"
            value={f.vt1_hr ?? ""}
            onChange={set("vt1_hr")}
          />
          {running ? (
            <Field
              id="lab-vt1pace"
              label="Primer umbral: ritmo (min/km)"
              placeholder="5:10"
              value={f.vt1_pace ?? ""}
              onChange={set("vt1_pace")}
            />
          ) : (
            <Field
              id="lab-vt1w"
              label="Primer umbral: vatios"
              value={f.vt1_power ?? ""}
              onChange={set("vt1_power")}
            />
          )}
          <Field
            id="lab-vt2hr"
            label="Segundo umbral (VT2/LT2): FC"
            value={f.vt2_hr ?? ""}
            onChange={set("vt2_hr")}
          />
          {running ? (
            <Field
              id="lab-vt2pace"
              label="Segundo umbral: ritmo (min/km)"
              placeholder="4:10"
              value={f.vt2_pace ?? ""}
              onChange={set("vt2_pace")}
            />
          ) : (
            <Field
              id="lab-vt2w"
              label="Segundo umbral: vatios"
              value={f.vt2_power ?? ""}
              onChange={set("vt2_power")}
            />
          )}
        </>
      ) : (
        <>
          <Field
            id="mt-lthr"
            label="FC umbral (ppm)"
            value={f.lthr ?? ""}
            onChange={set("lthr")}
          />
          {running ? (
            <Field
              id="mt-pace"
              label="Ritmo umbral (min/km)"
              placeholder="4:05"
              value={f.pace ?? ""}
              onChange={set("pace")}
            />
          ) : (
            <Field
              id="mt-ftp"
              label="FTP (vatios)"
              value={f.ftp ?? ""}
              onChange={set("ftp")}
            />
          )}
          <Field
            id="mt-vo2"
            label="VO2max (ml/kg/min)"
            mode="decimal"
            value={f.vo2max ?? ""}
            onChange={set("vo2max")}
          />
          <Field
            id="mt-hrmax"
            label="FC máxima (ppm)"
            value={f.hr_max ?? ""}
            onChange={set("hr_max")}
          />
        </>
      )}
      <div className="md:col-span-2">
        <Field
          id={`${id}-notes`}
          label="Notas (opcional)"
          mode="text"
          placeholder={
            lab
              ? "Ej. ergoespirometría en el centro X"
              : "Ej. test en pista con el club"
          }
          value={f.notes ?? ""}
          onChange={set("notes")}
        />
      </div>
      <p className="text-xs text-muted-foreground md:col-span-2">
        Mete solo lo que sepas. Se aplica al momento y manda sobre Garmin y las
        estimaciones durante 8 semanas.
      </p>
      <Actions pending={create.isPending} onCancel={onDone} />
    </form>
  );
}

/** CSS de natación con los tiempos del 400 y el 200. */
export function CssForm({ onDone }: { onDone: () => void }) {
  const create = useCreateManualTest();
  const [day, setDay] = useState(toIsoDay(new Date()));
  const [t400, setT400] = useState("");
  const [t200, setT200] = useState("");
  return (
    <form
      className="grid gap-3 rounded-lg border p-3 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const a = parseTime(t400);
        const b = parseTime(t200);
        if (!a || !b || Number.isNaN(a) || Number.isNaN(b)) {
          toast.error("Escribe los tiempos como m:ss, por ejemplo 6:20.");
          return;
        }
        create.mutate(
          {
            protocol: "swim_css",
            sport: "swimming",
            test_date: day,
            t400_s: a,
            t200_s: b,
          },
          {
            onSuccess: () => {
              toast.success("CSS guardado con tus zonas de natación.");
              onDone();
            },
            onError: (err) => toast.error(errorText(err)),
          },
        );
      }}
    >
      <SportAndDate
        idPrefix="css"
        sport="swimming"
        setSport={() => undefined}
        day={day}
        setDay={setDay}
        sports={["swimming"]}
      />
      <span className="hidden md:block" aria-hidden />
      <Field
        id="css-400"
        label="Tiempo en 400 m"
        placeholder="6:20"
        value={t400}
        onChange={setT400}
      />
      <Field
        id="css-200"
        label="Tiempo en 200 m"
        placeholder="2:58"
        value={t200}
        onChange={setT200}
      />
      <p className="text-xs text-muted-foreground md:col-span-2">
        Los dos a tope y con 5-10 min de descanso entre ellos. CSS = 200 m ÷
        (T400 − T200).
      </p>
      <Actions pending={create.isPending} onCancel={onDone} />
    </form>
  );
}

interface StepRow {
  lactate: string;
  intensity: string; // ritmo m:ss o vatios
  hr: string;
  lap?: number;
}

const emptyRows = (n: number): StepRow[] =>
  Array.from({ length: n }, () => ({ lactate: "", intensity: "", hr: "" }));

/**
 * Test de lactato escalonado: un escalón por fila con su lactato. Desde una actividad, cada vuelta es
 * un escalón y su ritmo/vatios y FC se toman de la vuelta: solo hay que meter el lactato.
 */
export function LactateForm({
  onDone,
  activity,
}: {
  onDone: () => void;
  activity?: { id: number; sport: string; date: string; laps: Lap[] };
}) {
  const create = useCreateLactateTest();
  const fromLaps = !!activity?.laps.length;
  const [sport, setSport] = useState<TestSport>(
    activity?.sport.includes("running") || !activity ? "running" : "cycling",
  );
  const cycling = sport === "cycling";
  const [day, setDay] = useState(activity?.date ?? toIsoDay(new Date()));
  const [rows, setRows] = useState<StepRow[]>(() =>
    fromLaps
      ? activity!.laps.map((l) => ({
          lap: l.index,
          lactate: "",
          hr: l.avg_hr ? String(Math.round(l.avg_hr)) : "",
          intensity: cycling
            ? String(Math.round(l.metrics?.avg_power ?? 0) || "")
            : l.avg_speed
              ? formatDuration(1000 / l.avg_speed)
              : "",
        }))
      : emptyRows(6),
  );
  const setRow = (i: number, patch: Partial<StepRow>) =>
    setRows((r) => r.map((row, k) => (k === i ? { ...row, ...patch } : row)));

  const submit = () => {
    const filled = rows.filter((r) => r.lactate.trim());
    if (filled.length < 4) {
      toast.error("Mete el lactato de al menos 4 escalones.");
      return;
    }
    const steps = filled.map((r) => {
      const pace = cycling ? null : parsePace(r.intensity);
      return {
        lactate: Number(r.lactate.replace(",", ".")),
        lap_index: r.lap ?? null,
        pace_s_km: r.lap == null && !cycling ? pace : null,
        power: r.lap == null && cycling ? num(r.intensity) : null,
        hr: r.lap == null ? num(r.hr) : null,
      };
    });
    if (
      steps.some((s) => Number.isNaN(s.lactate) || Number.isNaN(s.pace_s_km))
    ) {
      toast.error(
        "Revisa los valores: lactato con decimales y ritmo como m:ss.",
      );
      return;
    }
    create.mutate(
      {
        sport: cycling ? "cycling" : "running",
        test_date: day,
        activity_id: activity?.id ?? null,
        steps,
      },
      {
        onSuccess: (t) => {
          toast.success(`Umbrales calculados: ${t.summary}.`);
          onDone();
        },
        onError: (err) => toast.error(errorText(err)),
      },
    );
  };

  return (
    <form
      className="space-y-3 rounded-lg border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <SportAndDate
          idPrefix="lac"
          sport={sport}
          setSport={(s) => setSport(s)}
          day={day}
          setDay={setDay}
          sports={fromLaps ? [sport] : ["running", "cycling"]}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        {fromLaps
          ? "Cada vuelta de la actividad es un escalón: mete el lactato de las que fueran escalones y deja vacías el calentamiento y la vuelta a la calma."
          : `Un escalón por fila, del más suave al más duro: ${cycling ? "vatios" : "ritmo"}, FC media y lactato al terminar.`}
      </p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-10 py-1 font-normal">#</th>
            <th className="py-1 font-normal">{cycling ? "Vatios" : "Ritmo"}</th>
            <th className="py-1 font-normal">FC</th>
            <th className="py-1 font-normal">Lactato</th>
            {!fromLaps && <th className="w-11" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t">
              <td className="py-1 tabular-nums text-muted-foreground">
                {i + 1}
              </td>
              <td className="py-1 pr-1">
                <Input
                  aria-label={`Escalón ${i + 1}: ${cycling ? "vatios" : "ritmo"}`}
                  inputMode="numeric"
                  placeholder={cycling ? "200" : "5:00"}
                  disabled={r.lap != null}
                  className="h-11 md:h-9"
                  value={r.intensity}
                  onChange={(e) => setRow(i, { intensity: e.target.value })}
                />
              </td>
              <td className="py-1 pr-1">
                <Input
                  aria-label={`Escalón ${i + 1}: FC`}
                  inputMode="numeric"
                  disabled={r.lap != null}
                  className="h-11 md:h-9"
                  value={r.hr}
                  onChange={(e) => setRow(i, { hr: e.target.value })}
                />
              </td>
              <td className="py-1">
                <Input
                  aria-label={`Escalón ${i + 1}: lactato (mmol/L)`}
                  inputMode="decimal"
                  placeholder="mmol/L"
                  className="h-11 md:h-9"
                  value={r.lactate}
                  onChange={(e) => setRow(i, { lactate: e.target.value })}
                />
              </td>
              {!fromLaps && (
                <td className="py-1 pl-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-11 md:size-9"
                    aria-label={`Quitar el escalón ${i + 1}`}
                    disabled={rows.length <= 4}
                    onClick={() => setRows((x) => x.filter((_, k) => k !== i))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!fromLaps && rows.length < 20 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 md:min-h-8"
          onClick={() => setRows((x) => [...x, ...emptyRows(1)])}
        >
          <Plus aria-hidden /> Añadir escalón
        </Button>
      )}
      <p className="text-xs text-muted-foreground">
        LT1 = donde el lactato sube 0,5 mmol/L sobre tu basal. LT2 = Dmax
        modificado sobre tu curva (o 4 mmol/L si la curva no lo permite). El LT2
        da tu FC y {cycling ? "tu FTP" : "tu ritmo umbral"}.
      </p>
      <div className="grid md:grid-cols-2">
        <Actions pending={create.isPending} onCancel={onDone} />
      </div>
    </form>
  );
}
