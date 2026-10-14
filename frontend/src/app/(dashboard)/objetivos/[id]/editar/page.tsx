"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { GoalForm } from "@/components/goals/goal-form";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useGoalReport, useSaveGoal } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";

export default function EditarObjetivoPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { data, isPending, isError, refetch } = useGoalReport(id);
  const save = useSaveGoal(id);
  return (
    <section className="max-w-2xl space-y-4">
      <Link
        href={`/objetivos/${id}`}
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Volver
      </Link>
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Editar objetivo
      </h1>
      {isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar el objetivo."
          onRetry={() => refetch()}
        />
      ) : (
        <GoalForm
          initial={data.goal}
          submitLabel="Guardar cambios"
          onSubmit={async (body) => {
            try {
              await save.mutateAsync(body);
              toast.success("Objetivo actualizado");
              router.push(`/objetivos/${id}`);
            } catch (err) {
              toast.error(
                err instanceof ApiError ? err.message : "No se pudo guardar.",
              );
            }
          }}
        />
      )}
    </section>
  );
}
