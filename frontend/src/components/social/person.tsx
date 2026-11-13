"use client";

import { Check, Clock, Loader2, UserPlus } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useBlock, useFollow, useUnfollow } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { followLabel, initials } from "@/lib/social";
import { cn } from "@/lib/utils";
import type { FollowStatus, Person, PersonRef } from "@/types/api";

export const errorText = (e: unknown, fallback = "No se pudo completar.") =>
  e instanceof ApiError ? e.message : fallback;

/** Avatar con las iniciales del nombre visible (nunca foto ni email). */
export function PersonAvatar({
  name,
  size = "md",
  className,
}: {
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-klyp-navy-light font-semibold text-white dark:bg-klyp-accent",
        size === "sm" && "size-8 text-xs",
        size === "md" && "size-10 text-sm",
        size === "lg" && "size-16 text-xl",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}

/** Nombre y @ con enlace al perfil público. */
export function PersonName({
  person,
  className,
}: {
  person: PersonRef;
  className?: string;
}) {
  return (
    <Link
      href={`/u/${person.handle}`}
      className={cn("min-w-0 hover:underline", className)}
    >
      <span className="block truncate font-medium">{person.display_name}</span>
      <span className="block truncate text-xs text-muted-foreground">
        @{person.handle}
      </span>
    </Link>
  );
}

/**
 * Seguir / Pendiente / Siguiendo. Con una solicitud pendiente o siguiendo, al tocar se ofrece
 * cancelar o dejar de seguir (en un menú, para no hacerlo sin querer).
 */
export function FollowButton({
  userId,
  status,
  name,
  className,
}: {
  userId: number;
  status: FollowStatus;
  name: string;
  className?: string;
}) {
  const follow = useFollow();
  const unfollow = useUnfollow();
  const busy = follow.isPending || unfollow.isPending;
  const btn = cn("min-h-11 md:min-h-8", className);

  if (status === "none")
    return (
      <Button
        size="sm"
        className={btn}
        disabled={busy}
        onClick={() =>
          follow.mutate(userId, {
            onSuccess: (r) =>
              toast.success(
                r.status === "accepted"
                  ? `Ya sigues a ${name}.`
                  : `Solicitud enviada a ${name}.`,
              ),
            onError: (e) => toast.error(errorText(e)),
          })
        }
      >
        {busy ? <Loader2 className="animate-spin" /> : <UserPlus aria-hidden />}
        {followLabel(status)}
      </Button>
    );

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          variant="outline"
          className={btn}
          disabled={busy}
          aria-label={`${followLabel(status)}: opciones para ${name}`}
        >
          {busy ? (
            <Loader2 className="animate-spin" />
          ) : status === "pending" ? (
            <Clock aria-hidden />
          ) : (
            <Check aria-hidden />
          )}
          {followLabel(status)}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 space-y-2">
        <p className="text-sm">
          {status === "pending"
            ? `¿Cancelar la solicitud a ${name}?`
            : `¿Dejar de seguir a ${name}?`}
        </p>
        <Button
          variant="destructive"
          size="sm"
          className="min-h-11 w-full md:min-h-8"
          onClick={() =>
            unfollow.mutate(userId, {
              onSuccess: () =>
                toast.success(
                  status === "pending"
                    ? "Solicitud cancelada."
                    : `Has dejado de seguir a ${name}.`,
                ),
              onError: (e) => toast.error(errorText(e)),
            })
          }
        >
          {status === "pending" ? "Cancelar solicitud" : "Dejar de seguir"}
        </Button>
      </PopoverContent>
    </Popover>
  );
}

/** Fila de una persona: avatar, nombre, @, «Te sigue» y acciones a la derecha. */
export function PersonRow({
  person,
  actions,
}: {
  person: Person;
  actions?: React.ReactNode;
}) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <PersonAvatar name={person.display_name} />
      <div className="flex min-w-0 flex-1 flex-col">
        <PersonName person={person} />
        {person.follows_me && (
          <Badge variant="secondary" className="mt-0.5">
            Te sigue
          </Badge>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
        {actions}
      </div>
    </li>
  );
}

/** Desbloquear a alguien (en Personas → Bloqueados y en Ajustes → Privacidad social). */
export function UnblockButton({ person }: { person: Person }) {
  const block = useBlock();
  return (
    <Button
      size="sm"
      variant="outline"
      className="min-h-11 md:min-h-8"
      disabled={block.isPending}
      onClick={() =>
        block.mutate(
          { userId: person.user_id, block: false },
          {
            onSuccess: () =>
              toast.success(`Has desbloqueado a ${person.display_name}.`),
            onError: (e) => toast.error(errorText(e)),
          },
        )
      }
    >
      Desbloquear
    </Button>
  );
}
