"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowDown, ArrowUp, Loader2, Plus, Trash2 } from "lucide-react";
import {
  useFieldArray,
  useForm,
  useWatch,
  type Control,
  type UseFormRegister,
} from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDuration } from "@/lib/format";
import {
  BLOCK_KINDS,
  TARGET_METRICS,
  metricInfo,
  parseClock,
} from "@/lib/plan";
import { cn } from "@/lib/utils";
import type {
  BlockKind,
  PlannedBlock,
  PlannedSessionInput,
  TargetMetric,
} from "@/types/api";

const SPORTS = [
  { value: "running", label: "Carrera" },
  { value: "cycling", label: "Ciclismo" },
  { value: "strength_training", label: "Fuerza" },
  { value: "lap_swimming", label: "Natación" },
];

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

const blockSchema = z
  .object({
    kind: z.enum(["warmup", "steady", "interval", "recovery", "cooldown"]),
    repeat: z.coerce.number().int().min(1, "Mínimo 1").max(50, "Máximo 50"),
    measure: z.enum(["time", "distance", "open"]),
    amount: z.string(),
    target_metric: z.enum(["", "pace", "speed", "hr", "power", "cadence"]),
    target_min: z.string(),
    target_max: z.string(),
    recovery_measure: z.enum(["time", "distance"]),
    recovery_amount: z.string(),
  })
  .superRefine((b, ctx) => {
    if (b.measure === "time" && !parseClock(b.amount))
      ctx.addIssue({
        code: "custom",
        path: ["amount"],
        message: "Usa minutos o m:ss",
      });
    if (b.measure === "distance" && !(Number(b.amount) > 0))
      ctx.addIssue({
        code: "custom",
        path: ["amount"],
        message: "Metros mayores que 0",
      });
    if (b.target_metric) {
      const clock = metricInfo(b.target_metric).clock;
      const parse = (v: string) =>
        v.trim() ? (clock ? parseClock(v) : Number(v.replace(",", "."))) : null;
      const [lo, hi] = [parse(b.target_min), parse(b.target_max)];
      if (lo == null && hi == null)
        ctx.addIssue({
          code: "custom",
          path: ["target_min"],
          message: "Indica al menos un valor",
        });
      for (const [key, value, raw] of [
        ["target_min", lo, b.target_min],
        ["target_max", hi, b.target_max],
      ] as const) {
        if (raw.trim() && (value == null || Number.isNaN(value)))
          ctx.addIssue({
            code: "custom",
            path: [key],
            message: clock ? "Formato m:ss" : "Número no válido",
          });
      }
    }
    if (b.repeat > 1 && b.recovery_amount.trim()) {
      const ok =
        b.recovery_measure === "time"
          ? parseClock(b.recovery_amount)
          : Number(b.recovery_amount) > 0;
      if (!ok)
        ctx.addIssue({
          code: "custom",
          path: ["recovery_amount"],
          message: "Valor no válido",
        });
    }
  });

const schema = z.object({
  day: z.string().min(1, "Elige un día"),
  sport: z.string().min(1),
  title: z.string().trim().min(1, "Ponle un título").max(255),
  notes: z.string().max(2000),
  blocks: z.array(blockSchema).min(1, "Añade al menos un bloque").max(30),
});

type FormValues = z.input<typeof schema>;
type BlockForm = FormValues["blocks"][number];

const EMPTY_BLOCK: BlockForm = {
  kind: "steady",
  repeat: 1,
  measure: "time",
  amount: "",
  target_metric: "",
  target_min: "",
  target_max: "",
  recovery_measure: "time",
  recovery_amount: "",
};

function block(partial: Partial<BlockForm>): BlockForm {
  return { ...EMPTY_BLOCK, ...partial };
}

const TEMPLATES: { label: string; title: string; blocks: BlockForm[] }[] = [
  {
    label: "Rodaje",
    title: "Rodaje suave",
    blocks: [
      block({
        kind: "steady",
        amount: "45",
        target_metric: "hr",
        target_max: "150",
      }),
    ],
  },
  {
    label: "Series",
    title: "Series 6 × 1000 m",
    blocks: [
      block({ kind: "warmup", amount: "15" }),
      block({
        kind: "interval",
        repeat: 6,
        measure: "distance",
        amount: "1000",
        target_metric: "pace",
        target_min: "4:00",
        target_max: "4:10",
        recovery_amount: "1:30",
      }),
      block({ kind: "cooldown", amount: "10" }),
    ],
  },
  {
    label: "Tempo",
    title: "Tempo 20'",
    blocks: [
      block({ kind: "warmup", amount: "15" }),
      block({
        kind: "steady",
        amount: "20",
        target_metric: "pace",
        target_min: "4:30",
        target_max: "4:40",
      }),
      block({ kind: "cooldown", amount: "10" }),
    ],
  },
];

/** Bloque de la API → valores del formulario. */
function toForm(b: PlannedBlock): BlockForm {
  const clock = b.target_metric ? metricInfo(b.target_metric).clock : false;
  const show = (v: number | null) =>
    v == null ? "" : clock ? formatDuration(v) : String(v);
  return {
    kind: b.kind,
    repeat: b.repeat,
    measure: b.distance_m ? "distance" : b.duration_s ? "time" : "open",
    amount: b.distance_m
      ? String(b.distance_m)
      : b.duration_s
        ? formatDuration(b.duration_s)
        : "",
    target_metric: b.target_metric ?? "",
    target_min: show(b.target_min),
    target_max: show(b.target_max),
    recovery_measure: b.recovery_distance_m ? "distance" : "time",
    recovery_amount: b.recovery_distance_m
      ? String(b.recovery_distance_m)
      : b.recovery_duration_s
        ? formatDuration(b.recovery_duration_s)
        : "",
  };
}

/** Valores del formulario → bloque de la API (ritmos m:ss → s/km; min/max ordenados). */
function fromForm(b: BlockForm): PlannedBlock {
  const metric = (b.target_metric || null) as TargetMetric | null;
  const clock = metric ? metricInfo(metric).clock : false;
  const parse = (v: string) =>
    v.trim() ? (clock ? parseClock(v) : Number(v.replace(",", "."))) : null;
  let [lo, hi] = metric
    ? [parse(b.target_min), parse(b.target_max)]
    : [null, null];
  if (lo != null && hi != null && lo > hi) [lo, hi] = [hi, lo];
  const repeat = Number(b.repeat);
  const hasRecovery = repeat > 1 && b.recovery_amount.trim();
  return {
    kind: b.kind as BlockKind,
    repeat,
    duration_s: b.measure === "time" ? parseClock(b.amount) : null,
    distance_m: b.measure === "distance" ? Number(b.amount) : null,
    target_metric: metric,
    target_min: lo,
    target_max: hi,
    recovery_duration_s:
      hasRecovery && b.recovery_measure === "time"
        ? parseClock(b.recovery_amount)
        : null,
    recovery_distance_m:
      hasRecovery && b.recovery_measure === "distance"
        ? Number(b.recovery_amount)
        : null,
  };
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-destructive">{message}</p> : null;
}

interface BlockEditorProps {
  index: number;
  total: number;
  control: Control<FormValues>;
  register: UseFormRegister<FormValues>;
  errors?: Partial<Record<keyof BlockForm, { message?: string }>>;
  onMove: (to: number) => void;
  onRemove: () => void;
}

function BlockEditor({
  index,
  total,
  control,
  register,
  errors,
  onMove,
  onRemove,
}: BlockEditorProps) {
  const values = useWatch({ control, name: `blocks.${index}` });
  const metric = values?.target_metric;
  const unit = metric ? metricInfo(metric).unit : "";
  const clock = metric ? metricInfo(metric).clock : false;
  const id = (name: string) => `block-${index}-${name}`;

  return (
    <Card className="py-0 shadow-sm">
      <CardContent className="space-y-3 p-3 md:p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold">Bloque {index + 1}</span>
          <div className="flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9"
              aria-label="Subir bloque"
              disabled={index === 0}
              onClick={() => onMove(index - 1)}
            >
              <ArrowUp className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9"
              aria-label="Bajar bloque"
              disabled={index === total - 1}
              onClick={() => onMove(index + 1)}
            >
              <ArrowDown className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 text-destructive"
              aria-label="Quitar bloque"
              onClick={onRemove}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="col-span-2 space-y-1 md:col-span-1">
            <Label htmlFor={id("kind")}>Tipo</Label>
            <select
              id={id("kind")}
              className={selectClass}
              {...register(`blocks.${index}.kind`)}
            >
              {BLOCK_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor={id("repeat")}>Repeticiones</Label>
            <Input
              id={id("repeat")}
              type="number"
              inputMode="numeric"
              min={1}
              max={50}
              className="h-11 md:h-9"
              {...register(`blocks.${index}.repeat`)}
            />
            <FieldError message={errors?.repeat?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id("measure")}>Medida</Label>
            <select
              id={id("measure")}
              className={selectClass}
              {...register(`blocks.${index}.measure`)}
            >
              <option value="time">Tiempo</option>
              <option value="distance">Distancia</option>
              <option value="open">Libre</option>
            </select>
          </div>
          {values?.measure !== "open" && (
            <div className="col-span-2 space-y-1 md:col-span-1">
              <Label htmlFor={id("amount")}>
                {values?.measure === "distance"
                  ? "Metros"
                  : "Duración (min o m:ss)"}
              </Label>
              <Input
                id={id("amount")}
                inputMode={values?.measure === "distance" ? "numeric" : "text"}
                placeholder={
                  values?.measure === "distance" ? "1000" : "10 o 4:30"
                }
                className="h-11 md:h-9"
                aria-invalid={!!errors?.amount}
                {...register(`blocks.${index}.amount`)}
              />
              <FieldError message={errors?.amount?.message} />
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="col-span-2 space-y-1 md:col-span-1">
            <Label htmlFor={id("metric")}>Objetivo</Label>
            <select
              id={id("metric")}
              className={selectClass}
              {...register(`blocks.${index}.target_metric`)}
            >
              <option value="">Sin objetivo</option>
              {TARGET_METRICS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          {metric && (
            <>
              <div className="space-y-1">
                <Label htmlFor={id("min")}>
                  {clock ? "Desde (más rápido)" : "Mínimo"} {unit}
                </Label>
                <Input
                  id={id("min")}
                  placeholder={clock ? "4:00" : ""}
                  inputMode={clock ? "text" : "decimal"}
                  className="h-11 md:h-9"
                  aria-invalid={!!errors?.target_min}
                  {...register(`blocks.${index}.target_min`)}
                />
                <FieldError message={errors?.target_min?.message} />
              </div>
              <div className="space-y-1">
                <Label htmlFor={id("max")}>
                  {clock ? "Hasta (más lento)" : "Máximo"} {unit}
                </Label>
                <Input
                  id={id("max")}
                  placeholder={clock ? "4:10" : ""}
                  inputMode={clock ? "text" : "decimal"}
                  className="h-11 md:h-9"
                  aria-invalid={!!errors?.target_max}
                  {...register(`blocks.${index}.target_max`)}
                />
                <FieldError message={errors?.target_max?.message} />
              </div>
            </>
          )}
        </div>

        {Number(values?.repeat) > 1 && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="space-y-1">
              <Label htmlFor={id("rec-measure")}>Recuperación</Label>
              <select
                id={id("rec-measure")}
                className={selectClass}
                {...register(`blocks.${index}.recovery_measure`)}
              >
                <option value="time">Tiempo</option>
                <option value="distance">Distancia</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor={id("rec-amount")}>
                {values?.recovery_measure === "distance" ? "Metros" : "m:ss"}
              </Label>
              <Input
                id={id("rec-amount")}
                placeholder={
                  values?.recovery_measure === "distance" ? "200" : "1:30"
                }
                className="h-11 md:h-9"
                aria-invalid={!!errors?.recovery_amount}
                {...register(`blocks.${index}.recovery_amount`)}
              />
              <FieldError message={errors?.recovery_amount?.message} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface SessionFormProps {
  initial?: PlannedSessionInput;
  defaultDay?: string;
  submitLabel: string;
  onSubmit: (body: PlannedSessionInput) => Promise<unknown>;
}

export function SessionForm({
  initial,
  defaultDay,
  submitLabel,
  onSubmit,
}: SessionFormProps) {
  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? { ...initial, blocks: initial.blocks.map(toForm) }
      : {
          day: defaultDay ?? "",
          sport: "running",
          title: "",
          notes: "",
          blocks: [block({ amount: "" })],
        },
  });
  const { fields, append, remove, move, replace } = useFieldArray({
    control,
    name: "blocks",
  });

  const submit = handleSubmit((values) =>
    onSubmit({
      day: values.day,
      sport: values.sport,
      title: values.title.trim(),
      notes: values.notes,
      blocks: values.blocks.map(fromForm),
    }),
  );

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {!initial && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Plantillas:</span>
          {TEMPLATES.map((t) => (
            <Button
              key={t.label}
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() => {
                setValue("title", t.title);
                replace(t.blocks);
              }}
            >
              {t.label}
            </Button>
          ))}
        </div>
      )}

      <Card className="py-0 shadow-sm">
        <CardContent className="grid gap-3 p-3 md:grid-cols-3 md:p-4">
          <div className="space-y-1 md:col-span-3">
            <Label htmlFor="title">Título</Label>
            <Input
              id="title"
              className="h-11 md:h-9"
              aria-invalid={!!errors.title}
              {...register("title")}
            />
            <FieldError message={errors.title?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="day">Día</Label>
            <Input
              id="day"
              type="date"
              className="h-11 md:h-9"
              aria-invalid={!!errors.day}
              {...register("day")}
            />
            <FieldError message={errors.day?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sport">Deporte</Label>
            <select id="sport" className={selectClass} {...register("sport")}>
              {SPORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1 md:col-span-3">
            <Label htmlFor="notes">Notas</Label>
            <textarea
              id="notes"
              rows={2}
              className={cn(selectClass, "h-auto py-2")}
              {...register("notes")}
            />
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {fields.map((field, index) => (
          <BlockEditor
            key={field.id}
            index={index}
            total={fields.length}
            control={control}
            register={register}
            errors={errors.blocks?.[index] as BlockEditorProps["errors"]}
            onMove={(to) => move(index, to)}
            onRemove={() => remove(index)}
          />
        ))}
        <FieldError
          message={errors.blocks?.root?.message ?? errors.blocks?.message}
        />
        <Button
          type="button"
          variant="outline"
          className="min-h-11 w-full"
          onClick={() => append(block({}))}
        >
          <Plus aria-hidden /> Añadir bloque
        </Button>
      </div>

      <Button
        type="submit"
        className="min-h-11 w-full md:w-auto"
        disabled={isSubmitting}
      >
        {isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
        {submitLabel}
      </Button>
    </form>
  );
}
