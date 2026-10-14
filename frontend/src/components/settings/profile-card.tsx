"use client";

import { Loader2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { TimeChart } from "@/components/progress/time-chart";
import { Badge } from "@/components/ui/badge";
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
import { useProfile, useSaveProfile } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { Profile, Sex } from "@/types/api";

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

function Derived({ profile }: { profile: Profile }) {
  const p = profile.vo2max_percentile;
  const items = [
    profile.age != null && { label: "Edad", value: `${profile.age} años` },
    profile.hr_max != null && {
      label: "FC máxima",
      value: `${formatNumber(profile.hr_max)} ppm`,
      hint:
        profile.hr_max_source === "real"
          ? "la más alta registrada"
          : "estimada por edad (Tanaka)",
    },
    profile.bmi != null && {
      label: "IMC",
      value: formatNumber(profile.bmi, 1),
    },
    profile.stride_ratio != null && {
      label: "Zancada / altura",
      value: formatNumber(profile.stride_ratio, 2),
      hint: "media de tus últimas carreras",
    },
    p &&
      profile.vo2max != null && {
        label: "VO2max para tu edad",
        value:
          p.bound === "above"
            ? "> P95"
            : p.bound === "below"
              ? "< P5"
              : `P${p.percentile}`,
        hint: `${formatNumber(profile.vo2max)} vs mediana ${formatNumber(p.median, 1)} (${p.age_group} años)`,
      },
  ].filter(Boolean) as { label: string; value: string; hint?: string }[];
  if (!items.length) return null;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {items.map((i) => (
        <div key={i.label} className="rounded-lg bg-muted/60 p-3">
          <p className="text-xs text-muted-foreground">{i.label}</p>
          <p className="text-lg font-semibold tabular-nums">{i.value}</p>
          {i.hint && <p className="text-xs text-muted-foreground">{i.hint}</p>}
        </div>
      ))}
    </div>
  );
}

/** Perfil del atleta: se rellena desde Garmin y se puede editar. Afina FC máx., percentiles y ajuste por edad. */
export function ProfileCard() {
  const { data, isPending, isError } = useProfile();
  const save = useSaveProfile();
  const [form, setForm] = useState({
    birth_date: "",
    sex: "",
    weight_kg: "",
    height_cm: "",
  });

  useEffect(() => {
    if (!data) return;
    setForm({
      birth_date: data.birth_date ?? "",
      sex: data.sex ?? "",
      weight_kg: data.weight_kg != null ? String(data.weight_kg) : "",
      height_cm: data.height_cm != null ? String(data.height_cm) : "",
    });
  }, [data]);

  if (isPending) return <Skeleton className="h-64 w-full" />;
  if (isError) return null;

  const num = (v: string) => (v.trim() ? Number(v.replace(",", ".")) : null);
  const weights = data.weight_history.map((w) => ({
    t: new Date(`${w.day}T12:00:00`).getTime(),
    value: w.weight_kg,
  }));

  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 font-heading text-lg">
            <UserRound className="size-5 text-klyp-accent" aria-hidden /> Perfil
          </CardTitle>
          <CardDescription>
            Afina la FC máxima, la comparación de tu VO2max con tu edad y las
            marcas ajustadas por edad.
          </CardDescription>
        </div>
        <Badge variant="outline">
          {[data.birth_date, data.sex, data.weight_kg, data.height_cm].every(
            (v) => v == null,
          )
            ? "Sin datos"
            : data.source === "garmin"
              ? "Desde Garmin"
              : "Editado a mano"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="grid grid-cols-2 gap-3 md:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              {
                birth_date: form.birth_date || null,
                sex: (form.sex || null) as Sex | null,
                weight_kg: num(form.weight_kg),
                height_cm: num(form.height_cm),
              },
              {
                onSuccess: () => toast.success("Perfil guardado"),
                onError: (err) =>
                  toast.error(
                    err instanceof ApiError
                      ? err.message
                      : "No se pudo guardar.",
                  ),
              },
            );
          }}
        >
          <div className="col-span-2 space-y-1 md:col-span-1">
            <Label htmlFor="birth_date">Fecha de nacimiento</Label>
            <Input
              id="birth_date"
              type="date"
              value={form.birth_date}
              className="h-11 md:h-9"
              onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sex">Sexo</Label>
            <select
              id="sex"
              className={selectClass}
              value={form.sex}
              onChange={(e) => setForm({ ...form, sex: e.target.value })}
            >
              <option value="">Sin indicar</option>
              <option value="male">Hombre</option>
              <option value="female">Mujer</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="weight">Peso (kg)</Label>
            <Input
              id="weight"
              inputMode="decimal"
              value={form.weight_kg}
              className="h-11 md:h-9"
              onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="height">Altura (cm)</Label>
            <Input
              id="height"
              inputMode="decimal"
              value={form.height_cm}
              className="h-11 md:h-9"
              onChange={(e) => setForm({ ...form, height_cm: e.target.value })}
            />
          </div>
          <div className="col-span-2 md:col-span-4">
            <Button
              type="submit"
              className="min-h-11"
              disabled={save.isPending}
            >
              {save.isPending && (
                <Loader2 className="animate-spin" aria-hidden />
              )}{" "}
              Guardar perfil
            </Button>
          </div>
        </form>

        <Derived profile={data} />

        {weights.length >= 2 && (
          <figure>
            <figcaption className="mb-1 text-sm font-medium">
              Evolución del peso
            </figcaption>
            <TimeChart
              data={weights}
              unit="kg"
              height="h-32"
              format={(v) => formatNumber(v, 1)}
              series={[
                {
                  key: "value",
                  label: "Peso",
                  color: "var(--chart-1)",
                  kind: "line",
                },
              ]}
            />
          </figure>
        )}
      </CardContent>
    </Card>
  );
}
