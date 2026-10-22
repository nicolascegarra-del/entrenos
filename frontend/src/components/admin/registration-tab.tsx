"use client";

import { CircleAlert, CircleCheck, CircleHelp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminSettings, useSaveAdminSettings } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BasicLimits, RegistrationMode } from "@/types/api";

const MODES: { value: RegistrationMode; label: string; help: string }[] = [
  {
    value: "invite",
    label: "Solo con invitación",
    help: "Nadie puede crear una cuenta sin un enlace de invitación tuyo. La opción más segura.",
  },
  {
    value: "approval",
    label: "Con aprobación",
    help: "Cualquiera puede pedir una cuenta: confirma su email y entra cuando la apruebas en Usuarios (cuenta Básica).",
  },
  {
    value: "open",
    label: "Abierto",
    help: "Cualquiera con el enlace de la app crea su cuenta Básica al confirmar su email.",
  },
];

const LIMIT_FIELDS: {
  key: keyof BasicLimits;
  label: string;
  unit: string;
  min: number;
  max: number;
}[] = [
  {
    key: "basic_history_days",
    label: "Histórico de Garmin",
    unit: "días",
    min: 30,
    max: 3650,
  },
  {
    key: "basic_max_goals",
    label: "Objetivos activos",
    unit: "como máximo",
    min: 1,
    max: 50,
  },
  {
    key: "basic_max_sessions_week",
    label: "Sesiones planificadas",
    unit: "por semana",
    min: 1,
    max: 50,
  },
];

const saveError = (err: unknown) =>
  toast.error(err instanceof ApiError ? err.message : "No se pudo guardar.");

function Requirement({
  ok,
  children,
}: {
  ok: boolean | null;
  children: React.ReactNode;
}) {
  const Icon = ok == null ? CircleHelp : ok ? CircleCheck : CircleAlert;
  return (
    <p
      className={cn(
        "flex items-start gap-1.5 text-sm",
        ok === false && "text-destructive",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

/** Lista extra de dominios bloqueados (además de los emails temporales conocidos). */
function BlockedDomains({ initial }: { initial: string[] }) {
  const save = useSaveAdminSettings();
  const [text, setText] = useState(initial.join("\n"));
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { blocked_domains: text.split(/[\s,]+/).filter(Boolean) },
          {
            onSuccess: (data) => {
              setText(data.blocked_domains.join("\n"));
              toast.success("Dominios guardados.");
            },
            onError: saveError,
          },
        );
      }}
    >
      <Label htmlFor="blocked-domains">Dominios bloqueados</Label>
      <p className="text-xs text-muted-foreground">
        Los emails temporales conocidos (mailinator, yopmail…) ya están
        bloqueados. Añade otros, uno por línea; también se bloquean sus
        subdominios.
      </p>
      <textarea
        id="blocked-domains"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="ejemplo.com"
        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      />
      <Button
        type="submit"
        variant="outline"
        className="min-h-11 md:min-h-9"
        disabled={save.isPending}
      >
        Guardar dominios
      </Button>
    </form>
  );
}

/** Límites de las cuentas Básicas (quien se registra sin invitación). */
function BasicLimitsForm({ initial }: { initial: BasicLimits }) {
  const save = useSaveAdminSettings();
  const [values, setValues] = useState(initial);
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { limits: values },
          {
            onSuccess: (data) => {
              setValues(data.limits);
              toast.success("Límites guardados.");
            },
            onError: saveError,
          },
        );
      }}
    >
      <p className="text-sm font-medium">Límites de las cuentas Básicas</p>
      <p className="text-xs text-muted-foreground">
        Se aplican a quien se registra solo. Los invitados y quien pases a
        Completa (en Usuarios) no tienen límites.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {LIMIT_FIELDS.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <Label htmlFor={f.key}>{f.label}</Label>
            <div className="flex items-center gap-2">
              <Input
                id={f.key}
                type="number"
                inputMode="numeric"
                min={f.min}
                max={f.max}
                value={values[f.key]}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: Number(e.target.value) }))
                }
                className="h-11 w-24 md:h-9"
              />
              <span className="text-sm text-muted-foreground">{f.unit}</span>
            </div>
          </div>
        ))}
      </div>
      <Button
        type="submit"
        variant="outline"
        className="min-h-11 md:min-h-9"
        disabled={save.isPending}
      >
        Guardar límites
      </Button>
    </form>
  );
}

/** Modo de registro, protecciones del autoregistro, dominios bloqueados y límites. */
export function RegistrationTab() {
  const { data, isPending, isError, refetch } = useAdminSettings();
  const save = useSaveAdminSettings();
  if (isPending) return <Skeleton className="h-40" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudieron cargar los ajustes."
        onRetry={() => refetch()}
      />
    );
  return (
    <div className="space-y-5">
      <fieldset className="space-y-2" disabled={save.isPending}>
        <legend className="mb-2 text-sm text-muted-foreground">
          Cómo se crean las cuentas nuevas:
        </legend>
        {MODES.map((m) => (
          <label
            key={m.value}
            className={cn(
              "flex cursor-pointer gap-3 rounded-lg border p-3",
              data.registration_mode === m.value &&
                "border-klyp-accent bg-klyp-pale/50 dark:bg-klyp-navy-light/40",
            )}
          >
            <input
              type="radio"
              name="registration"
              className="mt-1 size-4 accent-klyp-accent"
              checked={data.registration_mode === m.value}
              onChange={() =>
                save.mutate(
                  { registration_mode: m.value },
                  {
                    onSuccess: () => toast.success(`Registro: ${m.label}.`),
                    onError: saveError,
                  },
                )
              }
            />
            <span>
              <span className="block font-medium">{m.label}</span>
              <span className="block text-sm text-muted-foreground">
                {m.help}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <section className="space-y-1.5 rounded-lg border p-3">
        <p className="text-sm font-medium">
          Protección del registro sin invitación
        </p>
        <Requirement ok={data.email_enabled}>
          {data.email_enabled
            ? "Confirmación por email activa: las cuentas sin confirmar se borran a las 48 h."
            : "Sin correo configurado: el registro sin invitación no está disponible (hace falta SMTP para confirmar el email)."}
        </Requirement>
        <Requirement ok={data.captcha_enabled ? true : null}>
          {data.captcha_enabled
            ? "Captcha anti-bots (Cloudflare Turnstile) activo."
            : "Sin captcha: añade TURNSTILE_SITE_KEY y TURNSTILE_SECRET_KEY en el servidor para activarlo."}
        </Requirement>
        <Requirement ok>Emails temporales bloqueados.</Requirement>
        <Requirement ok={data.email_enabled ? true : null}>
          Cuentas Básicas sin entrar en 6 meses: aviso por email y borrado 30
          días después si siguen sin entrar.
        </Requirement>
        {data.registration_mode !== "invite" && !data.email_enabled && (
          <p className="text-xs text-destructive">
            Ahora mismo solo se puede entrar con invitación.
          </p>
        )}
      </section>

      <BlockedDomains initial={data.blocked_domains} />
      <BasicLimitsForm initial={data.limits} />
    </div>
  );
}
