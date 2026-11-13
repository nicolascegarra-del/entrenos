"use client";

import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useAdminModules, useSaveModules } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { MODULE_INFO, type ModuleKey } from "@/lib/modules";

/** Admin → Módulos: valor general de cada parte de la app (sin borrar datos). */
export function ModulesTab() {
  const { data, isPending, isError, refetch } = useAdminModules();
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
        Valor general de cada parte de la app: lo tienen todas las cuentas salvo
        las que tengan uno propio (Usuarios → Módulos). Desactivar solo oculta:
        no se borra ningún dato y vuelve tal cual al activarlo. Los cambios
        tardan como mucho un minuto en llegar a quien ya tenga la app abierta.
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
