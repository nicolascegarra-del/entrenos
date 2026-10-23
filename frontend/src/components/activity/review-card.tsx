"use client";

import { Loader2, MessageSquare, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { askAboutActivity } from "@/components/activity/ask-ai";
import { Markdown } from "@/components/assistant/markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivityReview, useRequestReview } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { ActivitySummary } from "@/types/api";

/** Análisis del entreno escrito por la IA: en curso, listo (con regenerar y seguir preguntando) o error. */
export function ReviewCard({ activity }: { activity: ActivitySummary }) {
  const { data: review, isPending } = useActivityReview(activity.id);
  const request = useRequestReview(activity.id);
  const ask = () =>
    request.mutate(undefined, {
      onError: (err) =>
        toast.error(
          err instanceof ApiError
            ? err.message
            : "No se pudo pedir el análisis.",
        ),
    });

  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Sparkles className="size-5 text-klyp-accent" aria-hidden /> Análisis
          de la IA
        </CardTitle>
        {review?.status === "done" && (
          <Button
            variant="ghost"
            size="sm"
            className="min-h-11 text-muted-foreground md:min-h-8"
            disabled={request.isPending}
            onClick={ask}
          >
            <RefreshCw
              className={request.isPending ? "animate-spin" : ""}
              aria-hidden
            />{" "}
            Regenerar
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isPending ? (
          <Skeleton className="h-24" />
        ) : !review ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Pide a tu asistente un análisis de este entreno: cómo ha ido, qué
              te aporta, qué mejorar y qué toca los próximos días.
            </p>
            <Button
              className="min-h-11 md:min-h-9"
              disabled={request.isPending}
              onClick={ask}
            >
              {request.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Sparkles aria-hidden />
              )}
              Analizar este entreno
            </Button>
            <p className="text-xs text-muted-foreground">
              Puedes hacer que se analicen solos al sincronizar en{" "}
              <Link
                href="/ajustes/asistente"
                className="text-klyp-accent underline"
              >
                Ajustes → Asistente IA
              </Link>
              .
            </p>
          </div>
        ) : review.status === "pending" ? (
          <p
            className="flex items-center gap-2 text-sm text-muted-foreground"
            role="status"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Tu asistente está analizando el entreno…
          </p>
        ) : review.status === "error" ? (
          <div className="space-y-2">
            <p className="text-sm text-destructive">
              {review.error || "No se pudo generar el análisis."}
            </p>
            <Button
              variant="outline"
              className="min-h-11 md:min-h-9"
              disabled={request.isPending}
              onClick={ask}
            >
              <RefreshCw aria-hidden /> Reintentar
            </Button>
          </div>
        ) : (
          <>
            <div className="text-sm">
              <Markdown text={review.content} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
              <span className="text-xs text-muted-foreground">
                {review.model_label ? `${review.model_label} · ` : ""}Puede
                equivocarse; no es consejo médico.
              </span>
              <Button
                asChild
                variant="outline"
                size="sm"
                className="min-h-11 md:min-h-8"
              >
                <Link
                  href={`/asistente?q=${encodeURIComponent(askAboutActivity(activity))}`}
                >
                  <MessageSquare aria-hidden /> Seguir preguntando
                </Link>
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
