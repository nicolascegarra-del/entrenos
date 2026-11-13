"use client";

import { Users } from "lucide-react";
import Link from "next/link";

import { CommentThread, VisibilityChoice } from "@/components/social/feed-card";
import { PersonAvatar, PersonName } from "@/components/social/person";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useKudosList, useModuleOn, useSocialMe } from "@/hooks/use-api";
import type { ActivityDetail } from "@/types/api";

/**
 * Parte social en el detalle de una actividad tuya: quién la ve (seguidores / solo yo),
 * los 👏 recibidos y los comentarios. Oculta si el módulo está apagado o no tienes perfil social.
 */
export function ActivitySocial({ activity }: { activity: ActivityDetail }) {
  const on = useModuleOn("social");
  const { data: me } = useSocialMe(on);
  const profile = me?.profile;
  const { data: kudos } = useKudosList(activity.id, on && !!profile);
  if (!on || !me) return null;
  if (!profile)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Users className="size-4" aria-hidden />
        <span>
          Comparte tus entrenos con tus amigos desde{" "}
          <Link href="/social" className="text-klyp-accent underline">
            Amigos
          </Link>
          .
        </span>
      </p>
    );
  const visibility = activity.visibility ?? profile.default_activity_visibility;
  return (
    <Card className="shadow-sm" data-tour="activity-social">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Amigos</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <p className="text-sm font-medium">¿Quién ve esta actividad?</p>
          <VisibilityChoice activityId={activity.id} value={visibility} />
          <p className="text-xs text-muted-foreground">
            Tus seguidores ven distancia, tiempo, ritmo, desnivel, el mapa
            recortado y tus logros. Nunca la FC, la salud, tus notas ni la IA.
          </p>
        </div>
        {kudos && kudos.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">
              <span aria-hidden>👏</span> {kudos.length}{" "}
              {kudos.length === 1 ? "kudo" : "kudos"}
            </p>
            <ul className="flex flex-wrap gap-2">
              {kudos.map((p) => (
                <li
                  key={p.user_id}
                  className="flex items-center gap-2 rounded-full bg-muted/60 py-1 pr-3 pl-1"
                >
                  <PersonAvatar name={p.display_name} size="sm" />
                  <PersonName person={p} className="text-sm" />
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="space-y-1">
          <p className="text-sm font-medium">Comentarios</p>
          <CommentThread activityId={activity.id} />
        </div>
      </CardContent>
    </Card>
  );
}
