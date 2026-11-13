"use client";

import { ChevronRight, Swords, Trophy } from "lucide-react";
import Link from "next/link";

import { DuelScoreboard } from "@/components/social/duels";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useModuleOn, useSocialSummary } from "@/hooks/use-api";
import { gapText, ordinal, rivalOf } from "@/lib/social";

/**
 * Tarjetas de Hoy: «Tu semana entre amigos» (puesto y lo que falta para subir) y el duelo activo.
 * No salen si el módulo está apagado, no tienes perfil social o la API falla.
 */
export function SocialTodayCards() {
  const on = useModuleOn("social");
  const { data } = useSocialSummary(on);
  if (!on || !data?.has_profile) return null;
  const gap = gapText(data.metric, data.gap_to_next, data.next_name);
  const duel = data.active_duel;
  return (
    <div
      className="grid gap-4 md:gap-6 lg:grid-cols-2"
      data-tour="social-today"
    >
      <Card className="shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 font-heading text-lg">
            <Trophy className="size-5 text-klyp-accent" aria-hidden />
            Tu semana entre amigos
          </CardTitle>
          <Link
            href="/social/ranking"
            className="inline-flex min-h-11 items-center gap-1 text-sm text-klyp-accent hover:underline md:min-h-8"
          >
            Ver <ChevronRight className="size-4" aria-hidden />
          </Link>
        </CardHeader>
        <CardContent className="space-y-1">
          {data.friends === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no sigues a nadie.{" "}
              <Link
                href="/social/personas"
                className="text-klyp-accent underline"
              >
                Busca a tus amigos
              </Link>{" "}
              para picarte con ellos.
            </p>
          ) : (
            <>
              <p className="text-2xl font-semibold tabular-nums">
                {data.my_rank
                  ? `${ordinal(data.my_rank)} de ${data.friends + 1}`
                  : "—"}
              </p>
              <p className="text-sm text-muted-foreground">
                {data.my_rank === 1
                  ? "¡Vas primero en km esta semana! Que no te pillen."
                  : (gap ?? "Suma kilómetros para subir puestos.")}
              </p>
            </>
          )}
        </CardContent>
      </Card>
      {duel && (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2 font-heading text-lg">
              <Swords
                className="size-5 shrink-0 text-klyp-accent"
                aria-hidden
              />
              <span className="truncate">
                Duelo con {rivalOf(duel).display_name}
              </span>
            </CardTitle>
            <Link
              href="/social/duelos"
              className="inline-flex min-h-11 shrink-0 items-center gap-1 text-sm text-klyp-accent hover:underline md:min-h-8"
            >
              Ver <ChevronRight className="size-4" aria-hidden />
            </Link>
          </CardHeader>
          <CardContent>
            <DuelScoreboard duel={duel} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
