"use client";

import { Ban, Ellipsis, Lock, Pencil, Swords, UserX } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { NewDuelDialog } from "@/components/social/duels";
import { FeedCard, FeedSkeleton } from "@/components/social/feed-card";
import {
  errorText,
  FollowButton,
  PersonAvatar,
} from "@/components/social/person";
import { SocialGate } from "@/components/social/social-setup";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useBlock, useSocialMe, useSocialUser } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { normalizeHandle } from "@/lib/social";
import type { Person } from "@/types/api";

function BlockMenu({ person }: { person: Person }) {
  const block = useBlock();
  const toggle = () =>
    block.mutate(
      { userId: person.user_id, block: !person.blocked },
      {
        onSuccess: () =>
          toast.success(
            person.blocked
              ? `Has desbloqueado a ${person.display_name}.`
              : `Has bloqueado a ${person.display_name}.`,
          ),
        onError: (e) => toast.error(errorText(e)),
      },
    );
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="size-11 md:size-8"
          aria-label="Más opciones"
        >
          <Ellipsis aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-2">
        <p className="text-xs text-muted-foreground">
          {person.blocked
            ? "Podrá volver a encontrarte y seguirte."
            : "Dejaréis de seguiros, no te verá en búsquedas, feed, clasificación ni duelos."}
        </p>
        <Button
          variant={person.blocked ? "outline" : "destructive"}
          size="sm"
          className="min-h-11 w-full md:min-h-8"
          disabled={block.isPending}
          onClick={toggle}
        >
          {person.blocked ? <UserX aria-hidden /> : <Ban aria-hidden />}
          {person.blocked ? "Desbloquear" : "Bloquear"}
        </Button>
      </PopoverContent>
    </Popover>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function PublicProfileView({ handle }: { handle: string }) {
  const { data: me } = useSocialMe();
  const { data, isPending, isError, error, refetch } = useSocialUser(handle);
  const [duelOpen, setDuelOpen] = useState(false);

  if (isPending)
    return (
      <div className="space-y-3">
        <FeedSkeleton />
      </div>
    );
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return notFound ? (
      <EmptyState icon={UserX} title="Este perfil no existe">
        <p className="text-sm text-muted-foreground">
          Revisa el @ o búscalo en Personas.
        </p>
        <Button asChild className="min-h-11">
          <Link href="/social/personas">Buscar personas</Link>
        </Button>
      </EmptyState>
    ) : (
      <ErrorState
        message="No se pudo cargar el perfil."
        onRetry={() => refetch()}
      />
    );
  }

  const { person, counts } = data;
  const isMe = me?.profile?.user_id === person.user_id;
  const friends = person.follow_status === "accepted";

  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        back={{ href: "/social/personas", label: "Personas" }}
        title={person.display_name}
        subtitle={`@${person.handle}`}
      />
      <Card className="gap-0 py-0 shadow-sm">
        <CardContent className="space-y-4 p-4">
          <div className="flex items-start gap-4">
            <PersonAvatar name={person.display_name} size="lg" />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap gap-1">
                {person.visibility === "private" && (
                  <Badge variant="secondary">
                    <Lock aria-hidden /> Perfil privado
                  </Badge>
                )}
                {person.follows_me && (
                  <Badge variant="secondary">Te sigue</Badge>
                )}
                {person.blocked && <Badge variant="outline">Bloqueado</Badge>}
              </div>
              {person.bio && (
                <p className="text-sm break-words whitespace-pre-line">
                  {person.bio}
                </p>
              )}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 rounded-lg bg-muted/60 p-2">
            <Count label="Seguidores" value={counts.followers} />
            <Count label="Siguiendo" value={counts.following} />
            <Count label="Actividades" value={counts.activities} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {isMe ? (
              <Button asChild variant="outline" className="min-h-11 md:min-h-9">
                <Link href="/ajustes/privacidad">
                  <Pencil aria-hidden /> Editar perfil y privacidad
                </Link>
              </Button>
            ) : (
              <>
                {!person.blocked && (
                  <FollowButton
                    userId={person.user_id}
                    status={person.follow_status}
                    name={person.display_name}
                    className="md:min-h-9"
                  />
                )}
                {friends && !person.blocked && (
                  <Button
                    variant="outline"
                    className="min-h-11 md:min-h-9"
                    onClick={() => setDuelOpen(true)}
                  >
                    <Swords aria-hidden /> Retar
                  </Button>
                )}
                <div className="ml-auto">
                  <BlockMenu person={person} />
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {data.can_view ? (
        data.recent.length ? (
          <div className="space-y-3">
            <h2 className="font-heading text-lg font-semibold">
              Actividades recientes
            </h2>
            {data.recent.map((item) => (
              <FeedCard key={item.activity_id} item={item} />
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Aún no ha compartido actividades.
          </p>
        )
      ) : (
        <EmptyState icon={Lock} title="Este perfil es privado">
          <p className="max-w-sm text-sm text-muted-foreground">
            {person.follow_status === "pending"
              ? "Tu solicitud está pendiente: cuando la acepte verás sus entrenos."
              : "Síguele para ver sus entrenos. Tendrá que aceptar tu solicitud."}
          </p>
          {!person.blocked && person.follow_status === "none" && (
            <FollowButton
              userId={person.user_id}
              status={person.follow_status}
              name={person.display_name}
            />
          )}
        </EmptyState>
      )}
      {friends && (
        <NewDuelDialog
          open={duelOpen}
          onOpenChange={setDuelOpen}
          opponent={person}
        />
      )}
    </section>
  );
}

/** Perfil público de una persona (/u/@handle): enlace para compartir o abrir desde un QR. */
export default function PublicProfilePage() {
  const raw = decodeURIComponent(useParams<{ handle: string }>().handle ?? "");
  return (
    <SocialGate>
      <PublicProfileView handle={normalizeHandle(raw)} />
    </SocialGate>
  );
}
