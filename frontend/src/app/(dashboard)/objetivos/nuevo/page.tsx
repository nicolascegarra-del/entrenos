"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { GoalForm } from "@/components/goals/goal-form";
import { useSaveGoal } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";

export default function NuevoObjetivoPage() {
  const router = useRouter();
  const save = useSaveGoal();
  return (
    <section className="max-w-2xl space-y-4">
      <Link
        href="/objetivos"
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Objetivos
      </Link>
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Nuevo objetivo
      </h1>
      <GoalForm
        submitLabel="Crear objetivo"
        onSubmit={async (body) => {
          try {
            const goal = await save.mutateAsync(body);
            router.push(`/objetivos/${goal.id}`);
          } catch (err) {
            toast.error(
              err instanceof ApiError
                ? err.message
                : "No se pudo crear el objetivo.",
            );
          }
        }}
      />
    </section>
  );
}
