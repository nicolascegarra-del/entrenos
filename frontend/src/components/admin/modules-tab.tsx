"use client";

import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useModules, useSaveModules } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { MODULE_INFO, type ModuleKey } from "@/lib/modules";
import { cn } from "@/lib/utils";

/** Interruptor accesible (role="switch"), con área táctil de 44 px en el móvil. */
function Switch({
  id,
  checked,
  disabled,
  onChange,
  labelledBy,
  describedBy,
}: {
  id: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
  labelledBy: string;
  describedBy: string;
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-md focus-visible:outline-2 focus-visible:outline-klyp-accent disabled:opacity-60 md:min-h-8"
    >
      <span
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
          checked ? "bg-klyp-accent" : "bg-muted-foreground/30",
        )}
      >
        <span
          className={cn(
            "inline-block size-5 rounded-full bg-white shadow-sm transition-transform",
            checked ? "translate-x-5.5" : "translate-x-0.5",
          )}
        />
      </span>
    </button>
  );
}

/** Admin → Módulos: activar o desactivar partes de la app para todos (sin borrar datos). */
export function ModulesTab() {
  const { data, isPending, isError, refetch } = useModules();
  const save = useSaveModules();

  if (isPending) return <Skeleton className="h-64" />;
  if (isError || !data)
    return (
      <ErrorState
        message="No se pudieron cargar los módulos."
        onRetry={() => refetch()}
      />
    );

  const toggle = (key: ModuleKey, value: boolean) =>
    save.mutate(
      { [key]: value },
      {
        onSuccess: () =>
          toast.success(
            `${MODULE_INFO.find((m) => m.key === key)?.label}: ${value ? "activado" : "desactivado"}.`,
          ),
        onError: (err) =>
          toast.error(
            err instanceof ApiError ? err.message : "No se pudo guardar.",
          ),
      },
    );

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Activa o desactiva partes de la app para todos los usuarios. Desactivar
        solo las oculta: no se borra ningún dato y vuelven tal cual al
        activarlas. Los cambios tardan como mucho un minuto en llegar a quien ya
        tenga la app abierta.
      </p>
      <ul className="divide-y rounded-lg border">
        {MODULE_INFO.map(({ key, label, hint }) => (
          <li key={key} className="flex items-center gap-3 p-3">
            <div className="min-w-0 flex-1">
              <p id={`module-${key}-label`} className="text-sm font-medium">
                {label}
              </p>
              <p
                id={`module-${key}-hint`}
                className="text-xs text-muted-foreground"
              >
                {hint}
              </p>
            </div>
            {save.isPending && save.variables && key in save.variables && (
              <Loader2
                className="size-4 animate-spin text-muted-foreground"
                aria-hidden
              />
            )}
            <Switch
              id={`module-${key}`}
              checked={data[key]}
              disabled={save.isPending}
              onChange={(v) => toggle(key, v)}
              labelledBy={`module-${key}-label`}
              describedBy={`module-${key}-hint`}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
