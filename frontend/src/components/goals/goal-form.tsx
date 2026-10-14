"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDuration } from "@/lib/format";
import { parseClock } from "@/lib/plan";
import type { RaceGoalInput } from "@/types/api";

export const RACE_DISTANCES = [
  { value: "5000", label: "5 km" },
  { value: "10000", label: "10 km" },
  { value: "21097.5", label: "Media maratón (21,1 km)" },
  { value: "42195", label: "Maratón (42,2 km)" },
  { value: "free", label: "Otra distancia" },
];

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

const schema = z
  .object({
    name: z.string().trim().min(1, "Ponle un nombre").max(120),
    race_date: z.string().min(1, "Elige la fecha"),
    distance: z.string(),
    free_km: z.string(),
    target: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.distance === "free" && !(Number(v.free_km.replace(",", ".")) > 0))
      ctx.addIssue({
        code: "custom",
        path: ["free_km"],
        message: "Indica los km",
      });
    // h:mm:ss o mm:ss; un número suelto no se acepta para evitar ambigüedades.
    if (v.target.trim() && (!v.target.includes(":") || !parseClock(v.target)))
      ctx.addIssue({
        code: "custom",
        path: ["target"],
        message: "Formato h:mm:ss (ej. 0:50:00)",
      });
  });

type FormValues = z.infer<typeof schema>;

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-destructive">{message}</p> : null;
}

export function GoalForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: RaceGoalInput;
  submitLabel: string;
  onSubmit: (body: RaceGoalInput) => Promise<unknown>;
}) {
  const known =
    initial &&
    RACE_DISTANCES.some((d) => Number(d.value) === initial.distance_m);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: initial?.name ?? "",
      race_date: initial?.race_date ?? "",
      distance: initial
        ? known
          ? String(initial.distance_m)
          : "free"
        : "10000",
      free_km: initial && !known ? String(initial.distance_m / 1000) : "",
      target: initial?.target_time_s
        ? formatDuration(initial.target_time_s)
        : "",
    },
  });
  const distance = useWatch({ control, name: "distance" });

  const submit = handleSubmit((v) =>
    onSubmit({
      name: v.name.trim(),
      race_date: v.race_date,
      distance_m:
        v.distance === "free"
          ? Number(v.free_km.replace(",", ".")) * 1000
          : Number(v.distance),
      target_time_s: v.target.trim() ? parseClock(v.target) : null,
    }),
  );

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Card className="py-0 shadow-sm">
        <CardContent className="grid gap-3 p-3 md:grid-cols-2 md:p-4">
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="name">Carrera</Label>
            <Input
              id="name"
              placeholder="10K de mi ciudad"
              className="h-11 md:h-9"
              aria-invalid={!!errors.name}
              {...register("name")}
            />
            <FieldError message={errors.name?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="race_date">Fecha</Label>
            <Input
              id="race_date"
              type="date"
              className="h-11 md:h-9"
              aria-invalid={!!errors.race_date}
              {...register("race_date")}
            />
            <FieldError message={errors.race_date?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="distance">Distancia</Label>
            <select
              id="distance"
              className={selectClass}
              {...register("distance")}
            >
              {RACE_DISTANCES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          {distance === "free" && (
            <div className="space-y-1">
              <Label htmlFor="free_km">Kilómetros</Label>
              <Input
                id="free_km"
                inputMode="decimal"
                placeholder="15"
                className="h-11 md:h-9"
                aria-invalid={!!errors.free_km}
                {...register("free_km")}
              />
              <FieldError message={errors.free_km?.message} />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="target">Tiempo objetivo (opcional)</Label>
            <Input
              id="target"
              placeholder="0:55:00"
              className="h-11 md:h-9"
              aria-invalid={!!errors.target}
              {...register("target")}
            />
            <FieldError message={errors.target?.message} />
          </div>
        </CardContent>
      </Card>
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
