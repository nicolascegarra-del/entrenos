"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PersonRow, UnblockButton } from "@/components/social/person";
import { SocialSetup } from "@/components/social/social-setup";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useBlocked, useSaveSocialProfile, useSocialMe } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import {
  HANDLE_MAX,
  handleError,
  HIDE_MAP_OPTIONS,
  hideMapLabel,
  normalizeHandle,
} from "@/lib/social";
import { cn } from "@/lib/utils";
import type {
  ActivityVisibility,
  ProfileVisibility,
  SocialProfile,
} from "@/types/api";

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-base md:h-9 md:text-sm";

/** Fila con interruptor, título y ayuda. */
function SwitchRow({
  id,
  label,
  help,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-3">
      <div>
        <p id={`${id}-label`} className="text-sm font-medium">
          {label}
        </p>
        <p id={`${id}-help`} className="text-xs text-muted-foreground">
          {help}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onChange={onChange}
        labelledBy={`${id}-label`}
        describedBy={`${id}-help`}
      />
    </div>
  );
}

const PROFILE_OPTIONS: {
  value: ProfileVisibility;
  label: string;
  help: string;
}[] = [
  {
    value: "private",
    label: "Privado",
    help: "Apruebas a cada persona que quiere seguirte.",
  },
  {
    value: "public",
    label: "Público",
    help: "Cualquiera puede seguirte sin pedir permiso.",
  },
];

function PrivacyForm({ profile }: { profile: SocialProfile }) {
  const save = useSaveSocialProfile();
  const [form, setForm] = useState(profile);
  const [shareHistory, setShareHistory] = useState(false);
  const [handleTaken, setHandleTaken] = useState(false);
  const set = <K extends keyof SocialProfile>(k: K, v: SocialProfile[K]) =>
    setForm((f) => ({ ...f, [k]: v }));
  const hError = handleTaken
    ? "Ese @ ya lo usa otra persona."
    : handleError(form.handle);
  const nameError =
    form.display_name.trim().length < 2 ? "Escribe tu nombre visible." : null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (hError || nameError) return;
    save.mutate(
      {
        display_name: form.display_name.trim(),
        handle: form.handle,
        bio: form.bio.trim(),
        visibility: form.visibility,
        default_activity_visibility: form.default_activity_visibility,
        hide_map_ends_m: form.hide_map_ends_m,
        show_pace: form.show_pace,
        show_maps: form.show_maps,
        share_history: shareHistory,
      },
      {
        onSuccess: (p) => {
          setForm(p);
          toast.success("Privacidad guardada.");
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === "HANDLE_TAKEN")
            setHandleTaken(true);
          else
            toast.error(
              err instanceof ApiError ? err.message : "No se pudo guardar.",
            );
        },
      },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="font-heading text-lg">Tu perfil</CardTitle>
          <CardDescription>
            Lo que ven los demás. Nunca se muestra tu email.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="priv-name">Nombre visible</Label>
              <Input
                id="priv-name"
                value={form.display_name}
                maxLength={60}
                className="h-11 md:h-9"
                aria-invalid={!!nameError}
                onChange={(e) => set("display_name", e.target.value)}
              />
              {nameError && (
                <p className="text-xs text-destructive">{nameError}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="priv-handle">Tu @</Label>
              <Input
                id="priv-handle"
                value={form.handle}
                maxLength={HANDLE_MAX}
                autoCapitalize="none"
                spellCheck={false}
                className="h-11 md:h-9"
                aria-invalid={!!hError}
                aria-describedby="priv-handle-help"
                onChange={(e) => {
                  setHandleTaken(false);
                  set("handle", normalizeHandle(e.target.value));
                }}
              />
              <p
                id="priv-handle-help"
                className={cn(
                  "text-xs",
                  hError ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {hError ??
                  "Si lo cambias, tu enlace antiguo deja de funcionar."}
              </p>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="priv-bio">Sobre ti</Label>
            <textarea
              id="priv-bio"
              value={form.bio}
              maxLength={160}
              rows={2}
              placeholder="Corredor popular, preparando el maratón…"
              onChange={(e) => set("bio", e.target.value)}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm dark:bg-input/30"
            />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">
              Quién puede seguirte
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {PROFILE_OPTIONS.map((o) => (
                <label
                  key={o.value}
                  className={cn(
                    "flex min-h-11 cursor-pointer gap-2 rounded-lg border p-3",
                    form.visibility === o.value &&
                      "border-klyp-accent bg-klyp-accent/5",
                  )}
                >
                  <input
                    type="radio"
                    name="profile-visibility"
                    value={o.value}
                    checked={form.visibility === o.value}
                    onChange={() => set("visibility", o.value)}
                    className="mt-1 accent-klyp-accent"
                  />
                  <span>
                    <span className="block text-sm font-medium">{o.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {o.help}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </CardContent>
      </Card>

      <Card className="shadow-sm" data-tour="social-privacy">
        <CardHeader>
          <CardTitle className="font-heading text-lg">
            Tus actividades
          </CardTitle>
          <CardDescription>
            Nunca se comparten la FC, los datos de salud, tus notas ni los
            análisis de la IA.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="priv-default">Visibilidad por defecto</Label>
              <select
                id="priv-default"
                className={selectClass}
                value={form.default_activity_visibility}
                onChange={(e) =>
                  set(
                    "default_activity_visibility",
                    e.target.value as ActivityVisibility,
                  )
                }
              >
                <option value="followers">Visible para seguidores</option>
                <option value="private">Solo yo</option>
              </select>
              <p className="text-xs text-muted-foreground">
                Para las actividades nuevas. Cada una se cambia en su detalle.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="priv-hide">Zona oculta del mapa</Label>
              <select
                id="priv-hide"
                className={selectClass}
                value={form.hide_map_ends_m}
                onChange={(e) => set("hide_map_ends_m", Number(e.target.value))}
              >
                {HIDE_MAP_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {hideMapLabel(m)}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Se quita el trazado alrededor del inicio y del final (tu casa).
              </p>
            </div>
          </div>
          <div className="divide-y">
            <SwitchRow
              id="priv-pace"
              label="Mostrar ritmo y velocidad"
              help="Si lo apagas, se ven la distancia y el tiempo, pero no a qué ritmo."
              checked={form.show_pace}
              onChange={(v) => set("show_pace", v)}
            />
            <SwitchRow
              id="priv-maps"
              label="Mostrar mapas"
              help="El mini mapa de cada actividad, ya recortado."
              checked={form.show_maps}
              onChange={(v) => set("show_maps", v)}
            />
            <SwitchRow
              id="priv-history"
              label="Compartir también mi historial"
              help="Al guardar con esto activado, tus actividades anteriores pasan a «Visible para seguidores» (las que marcaste «Solo yo» siguen ocultas)."
              checked={shareHistory}
              onChange={setShareHistory}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button
          type="submit"
          className="min-h-11 w-full sm:w-auto"
          disabled={save.isPending}
        >
          {save.isPending && <Loader2 className="animate-spin" aria-hidden />}
          Guardar
        </Button>
      </div>
    </form>
  );
}

function BlockedCard() {
  const blocked = useBlocked();
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Bloqueados</CardTitle>
        <CardDescription>
          No te ven, no pueden seguirte ni retarte.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {blocked.isPending ? (
          <Skeleton className="h-12 w-full" />
        ) : blocked.isError ? (
          <ErrorState
            message="No se pudo cargar la lista."
            onRetry={() => blocked.refetch()}
          />
        ) : blocked.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No has bloqueado a nadie.
          </p>
        ) : (
          <ul className="divide-y">
            {blocked.data.map((p) => (
              <PersonRow
                key={p.user_id}
                person={p}
                actions={<UnblockButton person={p} />}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Ajustes → Privacidad social: perfil, visibilidad, mapa, ritmo y bloqueados. */
export function SocialPrivacyCard() {
  const { data, isPending, isError, refetch } = useSocialMe();
  if (isPending)
    return (
      <div className="space-y-3" role="status" aria-label="Cargando">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar tu privacidad."
        onRetry={() => refetch()}
      />
    );
  if (!data.profile) return <SocialSetup />;
  return (
    <>
      <PrivacyForm key={data.profile.user_id} profile={data.profile} />
      <BlockedCard />
    </>
  );
}
