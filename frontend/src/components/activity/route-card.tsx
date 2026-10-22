"use client";

import { GitCompare, Route } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useActivityRoute } from "@/hooks/use-api";
import { paceText } from "@/lib/compare";
import { formatDate } from "@/lib/format";

/** En el detalle de una actividad: si es un recorrido repetido, su puesto y accesos a comparar. */
export function RouteCard({ activityId }: { activityId: number }) {
  const { data } = useActivityRoute(activityId);
  if (!data) return null;
  const index = data.efforts.findIndex((e) => e.activity_id === activityId);
  const previous = index > 0 ? data.efforts[index - 1] : null;
  const best =
    data.best && data.best.activity_id !== activityId ? data.best : null;

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Route className="size-5 text-klyp-accent" aria-hidden /> Mismo
          recorrido
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">
          Has hecho <strong>{data.name}</strong> {data.count} veces.{" "}
          {data.rank === 1 ? (
            <strong>¡Es tu mejor ritmo en este recorrido!</strong>
          ) : data.rank ? (
            <>
              Por ritmo en movimiento, este intento es el{" "}
              <strong>{data.rank}.º</strong> de {data.count}
              {data.best && (
                <> (el mejor: {paceText(data.best.pace_s_km)} /km)</>
              )}
              .
            </>
          ) : null}
        </p>
        <div className="flex flex-wrap gap-2">
          {best && (
            <Button asChild className="min-h-11 md:min-h-9">
              <Link href={`/comparar?a=${best.activity_id}&b=${activityId}`}>
                <GitCompare aria-hidden /> Comparar con tu mejor
              </Link>
            </Button>
          )}
          {previous && previous.activity_id !== best?.activity_id && (
            <Button asChild variant="outline" className="min-h-11 md:min-h-9">
              <Link
                href={`/comparar?a=${previous.activity_id}&b=${activityId}`}
              >
                Con el anterior ({formatDate(`${previous.day}T12:00:00`)})
              </Link>
            </Button>
          )}
          <Button asChild variant="ghost" className="min-h-11 md:min-h-9">
            <Link href={`/recorridos/${data.id}`}>Ver todos los intentos</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
