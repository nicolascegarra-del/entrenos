"use client";

import {
  ChevronDown,
  Eye,
  EyeOff,
  Flag,
  Loader2,
  MessageCircle,
  Send,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { RouteThumb } from "@/components/routes/route-thumb";
import {
  errorText,
  PersonAvatar,
  PersonName,
} from "@/components/social/person";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAddComment,
  useComments,
  useDeleteComment,
  useKudosList,
  useSetActivityVisibility,
  useToggleKudos,
} from "@/hooks/use-api";
import { sportInfo } from "@/lib/format";
import { COMMENT_MAX, feedStats, relativeDate } from "@/lib/social";
import { cn } from "@/lib/utils";
import type { ActivityVisibility, FeedItem } from "@/types/api";

export const VISIBILITY_LABELS: Record<ActivityVisibility, string> = {
  followers: "Visible para seguidores",
  private: "Solo yo",
};

/** Lista de quién ha dado 👏 (se abre al tocar el número). */
function KudosListDialog({
  activityId,
  open,
  onOpenChange,
}: {
  activityId: number;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const { data, isPending, isError } = useKudosList(activityId, open);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>👏 Kudos</DialogTitle>
          <DialogDescription>
            Quién ha aplaudido esta actividad.
          </DialogDescription>
        </DialogHeader>
        {isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive" role="alert">
            No se pudo cargar la lista.
          </p>
        ) : data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aún nadie.</p>
        ) : (
          <ul className="divide-y">
            {data.map((p) => (
              <li key={p.user_id} className="flex items-center gap-3 py-2">
                <PersonAvatar name={p.display_name} size="sm" />
                <PersonName person={p} />
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** 👏 + contador. En las tuyas no puedes aplaudirte, pero ves quién lo ha hecho. */
export function KudosButton({ item }: { item: FeedItem }) {
  const toggle = useToggleKudos();
  const [listOpen, setListOpen] = useState(false);
  return (
    <div className="flex items-center">
      {!item.mine && (
        <Button
          variant={item.kudoed_by_me ? "secondary" : "ghost"}
          size="sm"
          className={cn(
            "min-h-11 min-w-11 text-lg md:min-h-9",
            item.kudoed_by_me && "ring-1 ring-klyp-accent/50",
          )}
          aria-pressed={item.kudoed_by_me}
          aria-label={item.kudoed_by_me ? "Quitar tu kudos" : "Dar kudos"}
          onClick={() =>
            toggle.mutate(
              { id: item.activity_id, give: !item.kudoed_by_me },
              { onError: (e) => toast.error(errorText(e)) },
            )
          }
        >
          <span aria-hidden>👏</span>
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="min-h-11 px-2 tabular-nums md:min-h-9"
        disabled={item.kudos_count === 0}
        onClick={() => setListOpen(true)}
        aria-label={`${item.kudos_count} kudos: ver quién`}
      >
        {item.mine && <span aria-hidden>👏</span>}
        {item.kudos_count}
      </Button>
      <KudosListDialog
        activityId={item.activity_id}
        open={listOpen}
        onOpenChange={setListOpen}
      />
    </div>
  );
}

/** Comentarios de una actividad con su caja de texto. */
export function CommentThread({ activityId }: { activityId: number }) {
  const { data, isPending, isError, refetch } = useComments(activityId, true);
  const add = useAddComment(activityId);
  const remove = useDeleteComment(activityId);
  const [body, setBody] = useState("");
  const inputId = `comentario-${activityId}`;
  const send = () => {
    const text = body.trim();
    if (!text) return;
    add.mutate(text, {
      onSuccess: () => setBody(""),
      onError: (e) => toast.error(errorText(e, "No se pudo enviar.")),
    });
  };
  return (
    <div className="space-y-3 border-t pt-3">
      {isPending ? (
        <Skeleton className="h-12 w-full" />
      ) : isError ? (
        <p className="text-sm text-destructive" role="alert">
          No se pudieron cargar los comentarios.{" "}
          <button className="underline" onClick={() => refetch()}>
            Reintentar
          </button>
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Sin comentarios todavía. ¡Anímale!
        </p>
      ) : (
        <ul className="space-y-2">
          {data.map((c) => (
            <li key={c.id} className="flex gap-2">
              <PersonAvatar name={c.author.display_name} size="sm" />
              <div className="min-w-0 flex-1 rounded-lg bg-muted/60 px-3 py-2">
                <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  <Link
                    href={`/u/${c.author.handle}`}
                    className="font-medium hover:underline"
                  >
                    {c.author.display_name}
                  </Link>
                  <span className="text-muted-foreground">
                    {relativeDate(c.created_at)}
                  </span>
                </p>
                <p className="text-sm break-words whitespace-pre-line">
                  {c.body}
                </p>
              </div>
              {c.can_delete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-11 shrink-0 md:size-8"
                  aria-label="Borrar comentario"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(c.id, {
                      onError: (e) => toast.error(errorText(e)),
                    })
                  }
                >
                  <Trash2 aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          Escribe un comentario
        </label>
        <textarea
          id={inputId}
          value={body}
          maxLength={COMMENT_MAX}
          rows={1}
          placeholder="Escribe un comentario…"
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          className="min-h-11 flex-1 resize-y rounded-md border border-input bg-transparent px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:min-h-9 md:text-sm dark:bg-input/30"
        />
        <Button
          type="submit"
          size="icon"
          className="size-11 shrink-0 md:size-9"
          disabled={!body.trim() || add.isPending}
          aria-label="Enviar comentario"
        >
          {add.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Send aria-hidden />
          )}
        </Button>
      </form>
    </div>
  );
}

/** «Visible para seguidores / Solo yo» para una actividad tuya. */
export function VisibilityChoice({
  activityId,
  value,
  compact = false,
}: {
  activityId: number;
  value: ActivityVisibility;
  compact?: boolean;
}) {
  const set = useSetActivityVisibility(activityId);
  const choose = (v: ActivityVisibility) =>
    v !== value &&
    set.mutate(v, {
      onSuccess: () =>
        toast.success(
          v === "private"
            ? "Ahora solo la ves tú."
            : "Ahora la ven tus seguidores.",
        ),
      onError: (e) => toast.error(errorText(e, "No se pudo guardar.")),
    });
  return (
    <div
      role="radiogroup"
      aria-label="Quién ve esta actividad"
      className={cn("flex gap-1", compact ? "flex-col" : "flex-wrap")}
    >
      {(["followers", "private"] as const).map((v) => {
        const Icon = v === "private" ? EyeOff : Eye;
        return (
          <Button
            key={v}
            role="radio"
            aria-checked={value === v}
            size="sm"
            variant={value === v ? "default" : "outline"}
            className="min-h-11 justify-start md:min-h-8"
            disabled={set.isPending}
            onClick={() => choose(v)}
          >
            <Icon aria-hidden />
            {VISIBILITY_LABELS[v]}
          </Button>
        );
      })}
    </div>
  );
}

/** Tarjeta de una actividad en el feed o en un perfil. */
export function FeedCard({ item }: { item: FeedItem }) {
  const [showComments, setShowComments] = useState(false);
  const { label, icon: Icon } = sportInfo(item.sport);
  const stats = feedStats(item);
  const title = item.name || label;
  return (
    <Card className="gap-0 py-0 shadow-sm">
      <CardContent className="space-y-3 p-3 md:p-4">
        <header className="flex items-center gap-3">
          <PersonAvatar name={item.owner.display_name} />
          <div className="min-w-0 flex-1">
            <PersonName person={item.owner} />
          </div>
          <p className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
            <Icon className="size-3.5" aria-hidden />
            <span>{label}</span>
            <span aria-hidden>·</span>
            <time dateTime={item.start_time}>
              {relativeDate(item.start_time)}
            </time>
          </p>
        </header>

        <div className="flex gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            <h3 className="font-heading text-base font-semibold break-words">
              {item.mine ? (
                <Link
                  href={`/actividades/${item.activity_id}`}
                  className="hover:underline"
                >
                  {title}
                </Link>
              ) : (
                title
              )}
            </h3>
            {(item.is_race || item.achievements.length > 0) && (
              <div className="flex flex-wrap gap-1">
                {item.is_race && (
                  <Badge>
                    <Flag aria-hidden /> Carrera
                  </Badge>
                )}
                {item.achievements.map((a) => (
                  <Badge key={`${a.kind}-${a.title}`} variant="secondary">
                    <span aria-hidden>🏅</span> {a.title}
                  </Badge>
                ))}
              </div>
            )}
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-4">
              {stats.map((s) => (
                <div key={s.label}>
                  <dt className="text-xs text-muted-foreground">{s.label}</dt>
                  <dd className="font-semibold tabular-nums">{s.value}</dd>
                </div>
              ))}
            </dl>
          </div>
          {item.track && item.track.length > 1 && (
            <RouteThumb
              preview={item.track}
              className="size-20 shrink-0 rounded-md bg-muted/60 sm:size-24"
            />
          )}
        </div>

        <footer className="flex flex-wrap items-center gap-1 border-t pt-1">
          <KudosButton item={item} />
          <Button
            variant="ghost"
            size="sm"
            className="min-h-11 md:min-h-9"
            aria-expanded={showComments}
            onClick={() => setShowComments((v) => !v)}
          >
            <MessageCircle aria-hidden />
            {item.comments_count}
            <span className="sr-only">comentarios</span>
            <ChevronDown
              aria-hidden
              className={cn(
                "transition-transform",
                showComments && "rotate-180",
              )}
            />
          </Button>
          {item.mine && (
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto min-h-11 text-muted-foreground md:min-h-9"
                  aria-label={`Quién la ve: ${VISIBILITY_LABELS[item.visibility]}`}
                >
                  {item.visibility === "private" ? (
                    <EyeOff aria-hidden />
                  ) : (
                    <Eye aria-hidden />
                  )}
                  <span className="max-sm:sr-only">
                    {VISIBILITY_LABELS[item.visibility]}
                  </span>
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-64 space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  ¿Quién ve esta actividad?
                </p>
                <VisibilityChoice
                  activityId={item.activity_id}
                  value={item.visibility}
                  compact
                />
              </PopoverContent>
            </Popover>
          )}
        </footer>
        {showComments && <CommentThread activityId={item.activity_id} />}
      </CardContent>
    </Card>
  );
}

export function FeedSkeleton() {
  return (
    <div className="space-y-3" role="status" aria-label="Cargando actividades">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-44 w-full" />
      ))}
    </div>
  );
}
