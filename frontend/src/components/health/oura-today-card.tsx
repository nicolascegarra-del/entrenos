"use client";

import { BedDouble, ChevronRight, CircleDot } from "lucide-react";
import Link from "next/link";

import { InfoTerm } from "@/components/glossary/info-term";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useHealthNight,
  useOuraEnabled,
  useOuraStatus,
  useRestPeriods,
} from "@/hooks/use-api";
import { formatNumber } from "@/lib/format";
import {
  formatDayShort,
  formatHm,
  recoveryFromOura,
  restPeriodOn,
} from "@/lib/oura";

function Figure({
  label,
  value,
  sub,
  term,
}: {
  label: string;
  value: string;
  sub?: string;
  term?: React.ComponentProps<typeof InfoTerm>["term"];
}) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {label}
        {term && <InfoTerm term={term} />}
      </p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** Aviso de Hoy cuando el modo descanso de Oura está activo. */
function RestModeNotice({ today }: { today: string }) {
  const { data } = useRestPeriods(today, today);
  const period = restPeriodOn(data, today);
  if (!period) return null;
  return (
    <p
      className="flex items-start gap-2 rounded-lg border border-klyp-accent/40 bg-klyp-accent/5 p-3 text-sm"
      role="status"
    >
      <BedDouble
        className="mt-0.5 size-4 shrink-0 text-klyp-accent"
        aria-hidden
      />
      <span>
        <span className="font-medium">Modo descanso activo</span> desde el{" "}
        {formatDayShort(period.start_date)}
        {period.end_date ? ` hasta el ${formatDayShort(period.end_date)}` : ""}.
        Prioriza recuperarte: mueve o suaviza las sesiones duras.
      </span>
    </p>
  );
}

/**
 * Recuperación de Hoy con los datos del anillo: readiness, sueño y HRV de la última noche.
 * Solo aparece si la fuente efectiva de recuperación es Oura.
 */
export function OuraTodayCard({ today }: { today: string }) {
  const on = useOuraEnabled();
  const { data: status } = useOuraStatus(on);
  const connected = on && !!status?.connected;
  const { data: night } = useHealthNight(today, connected);
  if (!on || !status?.connected) return null;
  const fromOura = recoveryFromOura(status, night?.source);
  const main = night?.main;
  const readiness = night?.readiness?.score;
  const sleepScore = night?.sleep_score;
  const hrv = main?.avg_hrv;
  const hasFigures =
    readiness != null || sleepScore != null || hrv != null || !!main;

  return (
    <div className="space-y-2">
      <RestModeNotice today={today} />
      {fromOura && hasFigures && (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 font-heading text-lg">
              <CircleDot className="size-5 text-klyp-accent" aria-hidden />
              Tu recuperación (Oura)
            </CardTitle>
            <Link
              href={`/progresion/salud/noche/${today}`}
              className="flex min-h-11 items-center gap-1 text-sm text-klyp-accent hover:underline"
            >
              Ver la noche <ChevronRight className="size-4" aria-hidden />
            </Link>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {readiness != null && (
              <Figure
                label="Readiness"
                term="readiness"
                value={formatNumber(readiness)}
                sub="de 100"
              />
            )}
            {sleepScore != null && (
              <Figure
                label="Sueño"
                value={formatNumber(sleepScore)}
                sub="de 100"
              />
            )}
            {main?.total_sleep_s != null && (
              <Figure
                label="Dormiste"
                value={formatHm(main.total_sleep_s)}
                sub={
                  main.efficiency != null
                    ? `eficiencia ${formatNumber(main.efficiency)} %`
                    : undefined
                }
              />
            )}
            {hrv != null && (
              <Figure label="HRV media" value={formatNumber(hrv)} sub="ms" />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
