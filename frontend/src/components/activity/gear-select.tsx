"use client";

import { Footprints } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { useGear, useSetActivityGear } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { ActivitySummary } from "@/types/api";

/** Zapatillas con las que se hizo una carrera (cambiar o quitar). */
export function GearSelect({ activity }: { activity: ActivitySummary }) {
  const { data: gear } = useGear();
  const setGear = useSetActivityGear(activity.id);
  if (!gear) return null;
  if (!gear.length)
    return (
      <Link
        href="/material"
        className="inline-flex min-h-11 items-center gap-1 text-xs text-klyp-accent underline md:min-h-0"
      >
        <Footprints className="size-3" aria-hidden /> Añadir zapatillas
      </Link>
    );
  // Las retiradas solo se ofrecen si esta actividad ya las tenía.
  const options = gear.filter((g) => !g.retired || g.id === activity.gear_id);
  return (
    <label className="inline-flex items-center gap-1 text-xs">
      <Footprints className="size-3" aria-hidden />
      <span className="sr-only">Zapatillas</span>
      <select
        className="h-11 max-w-48 truncate rounded-md border border-input bg-background px-2 text-xs md:h-7"
        value={activity.gear_id ?? ""}
        disabled={setGear.isPending}
        onChange={(e) =>
          setGear.mutate(e.target.value ? Number(e.target.value) : null, {
            onSuccess: () => toast.success("Zapatillas actualizadas."),
            onError: (err) =>
              toast.error(
                err instanceof ApiError ? err.message : "No se pudo guardar.",
              ),
          })
        }
      >
        <option value="">Sin zapatillas</option>
        {options.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </select>
    </label>
  );
}
