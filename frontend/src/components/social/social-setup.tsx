"use client";

import { Check, Loader2, Users, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

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
import { VisibilityChoice } from "@/components/social/profile-visibility";
import { Switch } from "@/components/ui/switch";
import { useSaveSocialProfile, useSocialMe } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import {
  HANDLE_MAX,
  handleError,
  normalizeHandle,
  suggestHandle,
} from "@/lib/social";

const SHARED = [
  "Distancia, tiempo, ritmo o velocidad y desnivel",
  "El mapa, sin los 300 m alrededor de tu casa (inicio y final)",
  "Tus logros y récords",
];
const NEVER = [
  "Frecuencia cardiaca y zonas",
  "Datos de salud (sueño, HRV, peso…)",
  "Tus notas y sensaciones",
  "Los análisis del entrenador IA",
];

/** Alta en la parte social: nombre visible, @ y qué se comparte (y qué nunca). */
export function SocialSetup() {
  const save = useSaveSocialProfile();
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [handleTouched, setHandleTouched] = useState(false);
  const [shareHistory, setShareHistory] = useState(false);
  const [visibility, setVisibility] = useState<"private" | "public">("private");
  const [serverError, setServerError] = useState<string | null>(null);

  const effectiveHandle = handleTouched ? handle : suggestHandle(name);
  const nameError =
    name.trim().length < 2 ? "Escribe tu nombre visible." : null;
  const hError = handleError(effectiveHandle);
  const [submitted, setSubmitted] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (nameError || hError) return;
    setServerError(null);
    save.mutate(
      {
        display_name: name.trim(),
        handle: effectiveHandle,
        visibility,
        share_history: shareHistory,
      },
      {
        onSuccess: () =>
          toast.success("¡Listo! Ya puedes buscar a tus amigos."),
        onError: (err) => {
          if (err instanceof ApiError && err.code === "HANDLE_TAKEN")
            setServerError("Ese @ ya lo usa otra persona: prueba con otro.");
          else
            toast.error(
              err instanceof ApiError ? err.message : "No se pudo guardar.",
            );
        },
      },
    );
  };

  const handleMsg = serverError ?? (submitted || handleTouched ? hError : null);

  return (
    <Card className="mx-auto max-w-2xl shadow-sm">
      <CardHeader>
        <div className="mb-2 flex size-12 items-center justify-center rounded-lg bg-klyp-pale text-klyp-accent dark:bg-muted">
          <Users className="size-6" aria-hidden />
        </div>
        <CardTitle className="font-heading text-xl">
          Entrena con tus amigos
        </CardTitle>
        <CardDescription>
          Sigue a tus amigos, dales 👏, compárate en la clasificación y rétales
          a un duelo. Primero, cómo quieres que te vean.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={submit} noValidate>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="social-name">Nombre visible</Label>
              <Input
                id="social-name"
                value={name}
                maxLength={60}
                autoComplete="nickname"
                className="h-11 md:h-9"
                aria-invalid={submitted && !!nameError}
                aria-describedby="social-name-help"
                onChange={(e) => setName(e.target.value)}
              />
              <p
                id="social-name-help"
                className={
                  submitted && nameError
                    ? "text-xs text-destructive"
                    : "text-xs text-muted-foreground"
                }
              >
                {submitted && nameError
                  ? nameError
                  : "Lo verán tus amigos. Nunca se muestra tu email."}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="social-handle">Tu @</Label>
              <div className="flex items-center rounded-md border border-input focus-within:ring-[3px] focus-within:ring-ring/50">
                <span className="pl-3 text-muted-foreground" aria-hidden>
                  @
                </span>
                <Input
                  id="social-handle"
                  value={effectiveHandle}
                  maxLength={HANDLE_MAX}
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  className="h-11 border-0 pl-1 shadow-none focus-visible:ring-0 md:h-9"
                  aria-invalid={!!handleMsg}
                  aria-describedby="social-handle-help"
                  onChange={(e) => {
                    setHandleTouched(true);
                    setServerError(null);
                    setHandle(normalizeHandle(e.target.value));
                  }}
                />
              </div>
              <p
                id="social-handle-help"
                className={
                  handleMsg
                    ? "text-xs text-destructive"
                    : "text-xs text-muted-foreground"
                }
                role={handleMsg ? "alert" : undefined}
              >
                {handleMsg ??
                  "Para que te encuentren. Letras minúsculas, números, «_» y «.» (3–30)."}
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-muted/60 p-3">
              <p className="mb-2 text-sm font-semibold">Qué se comparte</p>
              <ul className="space-y-1.5 text-sm">
                {SHARED.map((t) => (
                  <li key={t} className="flex gap-2">
                    <Check
                      className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
                      aria-hidden
                    />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg bg-muted/60 p-3">
              <p className="mb-2 text-sm font-semibold">
                Qué nunca se comparte
              </p>
              <ul className="space-y-1.5 text-sm">
                {NEVER.map((t) => (
                  <li key={t} className="flex gap-2">
                    <X
                      className="mt-0.5 size-4 shrink-0 text-destructive"
                      aria-hidden
                    />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <VisibilityChoice value={visibility} onChange={setVisibility} />
          <p className="text-xs text-muted-foreground">
            Cada actividad puede ser «Solo yo», y todo se puede cambiar después
            en Amigos → Personas o en Ajustes → Privacidad social.
          </p>

          <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
            <div>
              <p id="share-history-label" className="text-sm font-medium">
                Compartir también mi historial
              </p>
              <p
                id="share-history-help"
                className="text-xs text-muted-foreground"
              >
                Si lo dejas apagado, solo verán las actividades que hagas a
                partir de hoy.
              </p>
            </div>
            <Switch
              id="share-history"
              checked={shareHistory}
              onChange={setShareHistory}
              labelledBy="share-history-label"
              describedBy="share-history-help"
            />
          </div>

          <Button
            type="submit"
            className="min-h-11 w-full sm:w-auto"
            disabled={save.isPending}
          >
            {save.isPending && <Loader2 className="animate-spin" aria-hidden />}
            Empezar
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/**
 * Puerta de la parte social: mientras carga, esqueleto; si falla, error; si aún no tienes perfil,
 * el alta; si ya lo tienes, la pantalla.
 */
export function SocialGate({ children }: { children: React.ReactNode }) {
  const { data, isPending, isError, refetch } = useSocialMe();
  if (isPending)
    return (
      <div className="space-y-3" role="status" aria-label="Cargando">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar la parte social."
        onRetry={() => refetch()}
      />
    );
  if (!data.profile) return <SocialSetup />;
  return <>{children}</>;
}
