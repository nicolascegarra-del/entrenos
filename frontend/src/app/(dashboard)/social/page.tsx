"use client";

import { Loader2, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { FeedCard, FeedSkeleton } from "@/components/social/feed-card";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useSocialFeed } from "@/hooks/use-api";

/** Feed de Amigos: tus actividades y las de quien sigues, con scroll infinito. */
export default function SocialFeedPage() {
  const {
    data,
    isPending,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useSocialFeed();
  const sentinel = useRef<HTMLDivElement>(null);

  // Al acercarse al final, carga la página siguiente (el botón queda como alternativa).
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasNextPage || typeof IntersectionObserver === "undefined")
      return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "400px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const items = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="mx-auto max-w-2xl space-y-3">
      <PageHeader
        title="Amigos"
        subtitle="Lo último de quien sigues"
        hideTitleOnMobile
      />
      {isPending ? (
        <FeedSkeleton />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar el feed."
          onRetry={() => refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState icon={Users} title="Sigue a tus amigos">
          <p className="max-w-sm text-sm text-muted-foreground">
            Aquí verás sus entrenos para darles 👏 y comentar. Búscalos por su
            nombre o su @, o compárteles tu enlace.
          </p>
          <Button asChild className="min-h-11">
            <Link href="/social/personas">Buscar personas</Link>
          </Button>
        </EmptyState>
      ) : (
        <div className="space-y-3" data-tour="social-feed">
          {items.map((item) => (
            <FeedCard key={item.activity_id} item={item} />
          ))}
          <div ref={sentinel} aria-hidden />
          {hasNextPage ? (
            <div className="flex justify-center">
              <Button
                variant="outline"
                className="min-h-11"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage && (
                  <Loader2 className="animate-spin" aria-hidden />
                )}
                Cargar más
              </Button>
            </div>
          ) : (
            <p className="py-2 text-center text-xs text-muted-foreground">
              No hay más actividades.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
