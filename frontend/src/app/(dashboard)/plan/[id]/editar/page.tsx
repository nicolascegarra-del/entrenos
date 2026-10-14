"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { SessionForm } from "@/components/plan/session-form";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlan, useSavePlan } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";

export default function EditarSesionPage() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { data: plan, isPending, isError, refetch } = usePlan(id);
  const save = useSavePlan(id);

  return (
    <section className="max-w-3xl space-y-4">
      <Link
        href={`/plan/${id}`}
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Volver
      </Link>
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Editar sesión
      </h1>
      {isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar la sesión."
          onRetry={() => refetch()}
        />
      ) : (
        <SessionForm
          initial={plan}
          submitLabel="Guardar cambios"
          onSubmit={async (body) => {
            try {
              await save.mutateAsync(body);
              toast.success("Sesión actualizada");
              router.push(`/plan/${id}`);
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
