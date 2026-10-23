"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useDeleteActivities } from "@/hooks/use-api";

/** Borrar esta actividad (con confirmación); vuelve a la lista. */
export function DeleteActivity({ activityId }: { activityId: number }) {
  const router = useRouter();
  const remove = useDeleteActivities();
  return (
    <Button
      variant="ghost"
      className="min-h-11 w-full justify-start text-destructive md:min-h-9"
      disabled={remove.isPending}
      onClick={() => {
        if (
          !window.confirm(
            "¿Borrar esta actividad? Se quitan sus datos y no volverá a traerse al sincronizar. No se puede deshacer.",
          )
        )
          return;
        remove.mutate([activityId], {
          onSuccess: () => {
            toast.success("Actividad borrada.");
            router.push("/actividades");
          },
          onError: () => toast.error("No se pudo borrar."),
        });
      }}
    >
      {remove.isPending ? (
        <Loader2 className="animate-spin" />
      ) : (
        <Trash2 aria-hidden />
      )}
      Borrar actividad
    </Button>
  );
}
