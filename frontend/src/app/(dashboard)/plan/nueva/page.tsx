"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { SessionForm } from "@/components/plan/session-form";
import { useSavePlan } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { toIsoDay } from "@/lib/plan";

function NewSession() {
  const router = useRouter();
  const day = useSearchParams().get("dia") ?? toIsoDay(new Date());
  const save = useSavePlan();
  return (
    <SessionForm
      defaultDay={day}
      submitLabel="Guardar sesión"
      onSubmit={async (body) => {
        try {
          const plan = await save.mutateAsync(body);
          toast.success(
            plan.activity
              ? "Sesión guardada y comparada con tu actividad"
              : "Sesión planificada",
          );
          router.push(`/plan/${plan.id}`);
        } catch (err) {
          toast.error(
            err instanceof ApiError
              ? err.message
              : "No se pudo guardar la sesión.",
          );
        }
      }}
    />
  );
}

export default function NuevaSesionPage() {
  return (
    <section className="max-w-3xl space-y-4">
      <Link
        href="/plan"
        className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Plan
      </Link>
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Nueva sesión
      </h1>
      <Suspense>
        <NewSession />
      </Suspense>
    </section>
  );
}
