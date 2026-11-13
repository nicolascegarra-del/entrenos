"use client";

import { CircleCheck, Globe, Loader2, Lock } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { useSaveSocialProfile, useSocialMe } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SocialProfile } from "@/types/api";

type Visibility = SocialProfile["visibility"];

const OPTIONS: {
  value: Visibility;
  label: string;
  help: string;
  icon: typeof Lock;
}[] = [
  {
    value: "private",
    label: "Privado",
    help: "Apruebas a cada persona que quiere seguirte.",
    icon: Lock,
  },
  {
    value: "public",
    label: "Público",
    help: "Cualquiera con KTrain puede seguirte sin pedir permiso.",
    icon: Globe,
  },
];

/** Elección Privado / Público con su explicación (botones grandes, accesible como radio). */
export function VisibilityChoice({
  value,
  onChange,
  disabled,
  label = "¿Quién puede seguirte?",
}: {
  value: Visibility;
  onChange: (v: Visibility) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{label}</legend>
      <div
        role="radiogroup"
        aria-label={label}
        className="grid gap-2 sm:grid-cols-2"
      >
        {OPTIONS.map((o) => {
          const active = value === o.value;
          const Icon = o.icon;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => !active && onChange(o.value)}
              className={cn(
                "relative flex min-h-11 items-start gap-3 rounded-lg border p-3 text-left transition-colors disabled:opacity-60",
                active
                  ? "border-klyp-accent bg-klyp-accent/15 ring-2 ring-klyp-accent"
                  : "hover:bg-muted/60",
              )}
            >
              <Icon
                className={cn(
                  "mt-0.5 size-5 shrink-0",
                  active ? "text-klyp-accent" : "text-muted-foreground",
                )}
                aria-hidden
              />
              <span className="flex-1 pr-6">
                <span className="block text-sm font-medium">{o.label}</span>
                <span className="block text-xs text-muted-foreground">
                  {o.help}
                </span>
              </span>
              {active && (
                <CircleCheck
                  className="absolute top-3 right-3 size-5 text-klyp-accent"
                  aria-hidden
                />
              )}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/**
 * Amigos → Personas: tu perfil es privado o público, con cambio al momento. Al pasar a público se
 * avisa de que se aceptan las solicitudes pendientes.
 */
export function ProfileVisibilityCard() {
  const { data } = useSocialMe();
  const save = useSaveSocialProfile();
  const profile = data?.profile;
  if (!profile) return null;
  const pending = data?.counts.pending_requests ?? 0;

  const change = (visibility: Visibility) => {
    if (
      visibility === "public" &&
      pending > 0 &&
      !window.confirm(
        `Al hacer público tu perfil se aceptarán las ${pending} solicitudes pendientes. ¿Seguir?`,
      )
    )
      return;
    save.mutate(
      {
        display_name: profile.display_name,
        handle: profile.handle,
        visibility,
      },
      {
        onSuccess: () =>
          toast.success(
            visibility === "public"
              ? "Tu perfil ahora es público."
              : "Tu perfil ahora es privado: aprobarás a quien quiera seguirte.",
          ),
        onError: (err) =>
          toast.error(
            err instanceof ApiError ? err.message : "No se pudo guardar.",
          ),
      },
    );
  };

  return (
    <Card>
      <CardContent className="space-y-2 pt-4">
        <div className="flex items-center gap-2">
          <VisibilityChoice
            value={profile.visibility}
            onChange={change}
            disabled={save.isPending}
            label="Tu perfil"
          />
          {save.isPending && (
            <Loader2
              className="size-4 animate-spin text-muted-foreground"
              aria-hidden
            />
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Lo que ve cada uno de tus entrenos y la zona oculta del mapa, en{" "}
          <Link
            href="/ajustes/privacidad"
            className="text-klyp-accent underline"
          >
            Ajustes → Privacidad social
          </Link>
          .
        </p>
      </CardContent>
    </Card>
  );
}
