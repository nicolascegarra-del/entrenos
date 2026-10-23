"use client";

import {
  CircleAlert,
  CircleCheck,
  CircleX,
  Loader2,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useConfirmTest, useDeleteTest } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import {
  CONFIDENCE_LABEL,
  isActive,
  STATUS_LABEL,
  testValues,
} from "@/lib/tests";
import type { PerformanceTest } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

/**
 * Un test: valores, comprobaciones de calidad y acciones (aplicar a las zonas o borrar).
 * @param showActivity - enlace a la actividad (en el historial; no dentro de la propia actividad).
 */
export function TestResult({
  test,
  showActivity = false,
}: {
  test: PerformanceTest;
  showActivity?: boolean;
}) {
  const confirm = useConfirmTest();
  const remove = useDeleteTest();
  const values = testValues(test.results);
  const failed = test.status === "failed";
  const active = isActive(test);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{test.protocol_label}</span>
        <span className="text-sm text-muted-foreground">
          {formatDate(test.test_date)}
        </span>
        <Badge variant={failed ? "destructive" : "secondary"}>
          {active ? "Manda en tus zonas" : STATUS_LABEL[test.status]}
        </Badge>
        {!failed && test.confidence && test.source !== "manual" && (
          <span className="text-xs text-muted-foreground">
            {CONFIDENCE_LABEL[test.confidence]}
          </span>
        )}
      </div>

      {values.length > 0 && (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {values.map((v) => (
            <div key={v.key} className="rounded-lg bg-muted/60 p-2">
              <dt className="text-xs text-muted-foreground">{v.label}</dt>
              <dd className="font-heading text-lg font-semibold tabular-nums">
                {v.value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {test.results.hr_zones && (
        <details className="text-sm">
          <summary className="min-h-11 cursor-pointer content-center font-medium md:min-h-8">
            Zonas de FC en bici
          </summary>
          <ul className="mt-1 space-y-0.5 tabular-nums text-muted-foreground">
            {test.results.hr_zones.map((z) => (
              <li key={z.name}>
                {z.name}: {z.min}
                {z.max ? `–${z.max}` : "+"} ppm
              </li>
            ))}
          </ul>
        </details>
      )}

      {test.checks.length > 0 && (
        <ul className="space-y-1 text-sm">
          {test.checks.map((c) => (
            <li key={c.key} className="flex items-start gap-2">
              {c.ok ? (
                <CircleCheck
                  className="mt-0.5 size-4 shrink-0 text-emerald-600"
                  aria-label="Bien"
                />
              ) : c.critical ? (
                <CircleX
                  className="mt-0.5 size-4 shrink-0 text-destructive"
                  aria-label="Falla"
                />
              ) : (
                <CircleAlert
                  className="mt-0.5 size-4 shrink-0 text-amber-600"
                  aria-label="Atención"
                />
              )}
              <span className={c.ok ? "text-muted-foreground" : ""}>
                {c.message}
              </span>
            </li>
          ))}
        </ul>
      )}

      {test.notes && (
        <p className="text-sm text-muted-foreground">{test.notes}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {test.status === "detected" && (
          <Button
            className="min-h-11 md:min-h-9"
            disabled={confirm.isPending}
            onClick={() =>
              confirm.mutate(test.id, {
                onSuccess: () =>
                  toast.success(
                    "Aplicado: tus zonas y ritmos se han recalculado con este test.",
                  ),
                onError: (err) => toast.error(errorText(err)),
              })
            }
          >
            {confirm.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <CircleCheck aria-hidden />
            )}
            Aplicar a mis zonas
          </Button>
        )}
        <Button
          variant="ghost"
          className="min-h-11 text-muted-foreground md:min-h-9"
          disabled={remove.isPending}
          onClick={() => {
            if (
              test.status === "confirmed" &&
              !window.confirm(
                "¿Borrar este test? Tus zonas volverán a calcularse con Garmin o las estimaciones.",
              )
            )
              return;
            remove.mutate(test.id, {
              onError: (err) => toast.error(errorText(err)),
            });
          }}
        >
          <Trash2 aria-hidden />
          {test.status === "detected" ? "Descartar" : "Borrar"}
        </Button>
        {showActivity && test.activity_id && (
          <Link
            href={`/actividades/${test.activity_id}`}
            className="ml-auto text-sm text-klyp-accent underline"
          >
            {test.activity_name || "Ver la actividad"}
          </Link>
        )}
      </div>
      {failed && !showActivity && (
        <p className="text-xs text-muted-foreground">
          Puedes analizarla con otro tipo de test desde el menú «⋯» de la
          actividad.
        </p>
      )}
    </div>
  );
}
