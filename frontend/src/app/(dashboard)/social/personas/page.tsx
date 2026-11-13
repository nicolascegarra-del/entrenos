"use client";

import { Loader2, Search, UserX, Users } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import {
  errorText,
  FollowButton,
  PersonRow,
  UnblockButton,
} from "@/components/social/person";
import { ProfileVisibilityCard } from "@/components/social/profile-visibility";
import { ShareProfile } from "@/components/social/share-profile";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnswerRequest,
  useBlocked,
  useFollowers,
  useFollowing,
  useFollowRequests,
  usePeopleSearch,
  useRemoveFollower,
  useSocialMe,
} from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import type { Person } from "@/types/api";

type Tab = "requests" | "following" | "followers" | "blocked";

/** Lista con sus estados de carga, error y vacío. */
function PeopleList({
  query,
  empty,
  actions,
}: {
  query: {
    data?: Person[];
    isPending: boolean;
    isError: boolean;
    refetch: () => unknown;
  };
  empty: string;
  actions: (p: Person) => React.ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="space-y-2 py-2" role="status" aria-label="Cargando">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  if (query.isError)
    return (
      <ErrorState
        message="No se pudo cargar la lista."
        onRetry={() => query.refetch()}
      />
    );
  if (!query.data?.length)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>
    );
  return (
    <ul className="divide-y">
      {query.data.map((p) => (
        <PersonRow key={p.user_id} person={p} actions={actions(p)} />
      ))}
    </ul>
  );
}

function RequestActions({ person }: { person: Person }) {
  const answer = useAnswerRequest();
  const go = (accept: boolean) =>
    answer.mutate(
      { userId: person.user_id, accept },
      {
        onSuccess: () =>
          toast.success(
            accept
              ? `${person.display_name} ya te sigue.`
              : "Solicitud rechazada.",
          ),
        onError: (e) => toast.error(errorText(e)),
      },
    );
  return (
    <>
      <Button
        size="sm"
        className="min-h-11 md:min-h-8"
        disabled={answer.isPending}
        onClick={() => go(true)}
      >
        {answer.isPending && <Loader2 className="animate-spin" />}
        Aceptar
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 md:min-h-8"
        disabled={answer.isPending}
        onClick={() => go(false)}
      >
        Rechazar
      </Button>
    </>
  );
}

function RemoveFollower({ person }: { person: Person }) {
  const remove = useRemoveFollower();
  return (
    <Button
      size="sm"
      variant="outline"
      className="min-h-11 md:min-h-8"
      disabled={remove.isPending}
      onClick={() =>
        remove.mutate(person.user_id, {
          onSuccess: () =>
            toast.success(`${person.display_name} ya no te sigue.`),
          onError: (e) => toast.error(errorText(e)),
        })
      }
    >
      Quitar
    </Button>
  );
}

/** Personas: buscar, solicitudes, a quién sigues, quién te sigue y bloqueados. */
export default function PersonasPage() {
  const { data: me } = useSocialMe();
  const [q, setQ] = useState("");
  const deferred = useDeferredValue(q);
  const search = usePeopleSearch(deferred);
  const pending = me?.counts.pending_requests ?? 0;
  const [tab, setTab] = useState<Tab>(pending ? "requests" : "following");
  const requests = useFollowRequests(tab === "requests");
  const following = useFollowing(tab === "following");
  const followers = useFollowers(tab === "followers");
  const blocked = useBlocked(tab === "blocked");

  const TABS: { key: Tab; label: string; count?: number }[] = [
    { key: "requests", label: "Solicitudes", count: pending },
    { key: "following", label: "Siguiendo", count: me?.counts.following },
    { key: "followers", label: "Seguidores", count: me?.counts.followers },
    { key: "blocked", label: "Bloqueados" },
  ];
  const searching = deferred.trim().length >= 2;

  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Personas"
        subtitle="Busca a tus amigos y gestiona quién te sigue"
        hideTitleOnMobile
      />
      {me?.profile && <ProfileVisibilityCard />}
      {me?.profile && <ShareProfile handle={me.profile.handle} />}

      <div className="relative">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <label htmlFor="people-search" className="sr-only">
          Buscar por nombre o @
        </label>
        <Input
          id="people-search"
          type="search"
          value={q}
          placeholder="Buscar por nombre o @"
          className="h-11 pl-9"
          autoComplete="off"
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {searching ? (
        <Card className="gap-0 py-0 shadow-sm">
          <CardContent className="px-3 md:px-4">
            <PeopleList
              query={search}
              empty="No hay nadie con ese nombre o @."
              actions={(p) =>
                p.blocked ? (
                  <UnblockButton person={p} />
                ) : (
                  <FollowButton
                    userId={p.user_id}
                    status={p.follow_status}
                    name={p.display_name}
                  />
                )
              }
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <div
            role="tablist"
            aria-label="Listas de personas"
            className="flex gap-1 overflow-x-auto border-b [scrollbar-width:none]"
          >
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                id={`tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls="people-panel"
                onClick={() => setTab(t.key)}
                className={cn(
                  "flex min-h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 text-sm font-medium whitespace-nowrap transition-colors",
                  tab === t.key
                    ? "border-klyp-accent text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label}
                {t.count != null && t.count > 0 && (
                  <span
                    className={cn(
                      "rounded-full px-1.5 text-xs tabular-nums",
                      t.key === "requests"
                        ? "bg-klyp-accent text-white"
                        : "bg-muted",
                    )}
                  >
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>
          <div id="people-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === "requests" && (
              <PeopleList
                query={requests}
                empty="No tienes solicitudes pendientes."
                actions={(p) => <RequestActions person={p} />}
              />
            )}
            {tab === "following" && (
              <PeopleList
                query={following}
                empty="Aún no sigues a nadie. Búscalos arriba por su nombre o @."
                actions={(p) => (
                  <FollowButton
                    userId={p.user_id}
                    status={p.follow_status}
                    name={p.display_name}
                  />
                )}
              />
            )}
            {tab === "followers" && (
              <PeopleList
                query={followers}
                empty="Aún no te sigue nadie. Comparte tu enlace."
                actions={(p) => (
                  <>
                    {p.follow_status === "none" && (
                      <FollowButton
                        userId={p.user_id}
                        status={p.follow_status}
                        name={p.display_name}
                      />
                    )}
                    <RemoveFollower person={p} />
                  </>
                )}
              />
            )}
            {tab === "blocked" && (
              <PeopleList
                query={blocked}
                empty="No has bloqueado a nadie."
                actions={(p) => <UnblockButton person={p} />}
              />
            )}
          </div>
          {tab === "following" &&
            !following.isPending &&
            !following.data?.length && (
              <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                <Users className="size-4" aria-hidden /> Seguir a alguien con
                perfil privado le envía una solicitud.
              </p>
            )}
          {tab === "blocked" && (
            <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
              <UserX className="size-4" aria-hidden /> Quien está bloqueado no
              te ve ni puede seguirte o retarte.
            </p>
          )}
        </>
      )}
    </section>
  );
}
