"use client";

import { ShieldAlert, Trophy } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import {
  PeriodPicker,
  PeriodProvider,
  usePeriod,
} from "@/components/progress/period";
import { EmptyState } from "@/components/states";
import { useActivities, useInsights } from "@/hooks/use-api";

function Shell({ children }: { children: React.ReactNode }) {
  const { days } = usePeriod();
  // Hay datos si hay alguna actividad (de Garmin o importada de otro reloj, que no tiene dispositivo).
  const { data: activities } = useActivities(null);
  const { data: insights } = useInsights(days);
  if (activities && activities.pages[0]?.items.length === 0)
    return (
      <EmptyState icon={Trophy} title="Aún no hay actividades">
        <p className="text-sm text-muted-foreground">
          Sincroniza Garmin desde{" "}
          <Link
            href="/ajustes"
            className="font-medium text-klyp-accent underline"
          >
            Ajustes
          </Link>{" "}
          para ver tu evolución.
        </p>
      </EmptyState>
    );
  return (
    <section className="space-y-4 md:space-y-6">
      <PageHeader
        title="Progreso"
        hideTitleOnMobile
        actions={<PeriodPicker />}
      />
      {children}
      {insights && (
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {insights.disclaimer}
        </p>
      )}
    </section>
  );
}

/** Progreso: periodo común y aviso, con Forma, Rendimiento y Salud como subsecciones. */
export default function ProgresoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <PeriodProvider>
      <Shell>{children}</Shell>
    </PeriodProvider>
  );
}
