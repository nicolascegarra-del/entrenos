"use client";

import { CircleAlert, CircleCheck, Loader2, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useEmailSettings,
  useSaveEmailSettings,
  useTestEmail,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  EmailSettings,
  EmailSettingsInput,
  SmtpSecurity,
} from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const selectClass =
  "h-11 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

/** Valores típicos de proveedores habituales para rellenar el formulario de un toque. */
const PRESETS: {
  label: string;
  host: string;
  port: number;
  security: SmtpSecurity;
  hint: string;
}[] = [
  {
    label: "Gmail",
    host: "smtp.gmail.com",
    port: 587,
    security: "starttls",
    hint: "Usuario: tu dirección de Gmail. Contraseña: una «contraseña de aplicación» (myaccount.google.com/apppasswords; requiere verificación en dos pasos).",
  },
  {
    label: "Brevo",
    host: "smtp-relay.brevo.com",
    port: 587,
    security: "starttls",
    hint: "Usuario y clave SMTP en el panel de Brevo → SMTP & API. El remitente debe estar verificado en Brevo.",
  },
  {
    label: "Outlook",
    host: "smtp-mail.outlook.com",
    port: 587,
    security: "starttls",
    hint: "Usuario: tu dirección de Outlook/Hotmail. Puede requerir una contraseña de aplicación.",
  },
  {
    label: "Resend",
    host: "smtp.resend.com",
    port: 465,
    security: "ssl",
    hint: "Usuario: resend. Contraseña: tu API key de Resend. Requiere un dominio verificado.",
  },
];

const MODE_TEXT: Record<EmailSettings["mode"], string> = {
  smtp: "Enviando emails por SMTP.",
  file: "Modo de prueba: los emails se guardan en una carpeta del servidor y no se envían.",
  disabled:
    "Sin correo: no se envían emails (ni registro sin invitación ni recuperar contraseña por email).",
};

function StatusBanner({ data }: { data: EmailSettings }) {
  const ok = data.mode === "smtp";
  const Icon = ok ? CircleCheck : CircleAlert;
  return (
    <p
      className={cn(
        "flex items-start gap-2 rounded-lg border p-3 text-sm",
        ok
          ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
          : "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>
        {MODE_TEXT[data.mode]}{" "}
        {data.source === "panel"
          ? "Configuración de este panel."
          : data.env_configured
            ? "Configuración de las variables de entorno del servidor (guardar aquí la sustituye)."
            : ""}
      </span>
    </p>
  );
}

function EmailForm({ data }: { data: EmailSettings }) {
  const save = useSaveEmailSettings();
  const test = useTestEmail();
  const [form, setForm] = useState<Omit<EmailSettingsInput, "password">>({
    enabled: data.source === "panel" ? data.enabled : true,
    host: data.host,
    port: data.port,
    security: data.security,
    user: data.user,
    sender: data.sender,
    public_url: data.public_url,
  });
  const [password, setPassword] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { ...form, password: password ? password : null },
          {
            onSuccess: () => {
              setPassword("");
              toast.success("Correo guardado. Envía un email de prueba.");
            },
            onError: (err) => toast.error(errorText(err)),
          },
        );
      }}
    >
      <div className="space-y-1.5">
        <p className="text-sm font-medium">Proveedor</p>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <Button
              key={p.label}
              type="button"
              size="sm"
              variant={form.host === p.host ? "default" : "outline"}
              className="min-h-11 md:min-h-8"
              onClick={() => {
                setForm((f) => ({
                  ...f,
                  host: p.host,
                  port: p.port,
                  security: p.security,
                }));
                setHint(p.hint);
              }}
            >
              {p.label}
            </Button>
          ))}
        </div>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_7rem_10rem]">
        <div className="space-y-1.5">
          <Label htmlFor="smtp-host">Servidor SMTP</Label>
          <Input
            id="smtp-host"
            required
            value={form.host}
            onChange={(e) => set("host", e.target.value.trim())}
            placeholder="smtp.tuproveedor.com"
            className="h-11 md:h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="smtp-port">Puerto</Label>
          <Input
            id="smtp-port"
            type="number"
            inputMode="numeric"
            min={1}
            max={65535}
            required
            value={form.port}
            onChange={(e) => set("port", Number(e.target.value))}
            className="h-11 md:h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="smtp-security">Seguridad</Label>
          <select
            id="smtp-security"
            className={selectClass}
            value={form.security}
            onChange={(e) => set("security", e.target.value as SmtpSecurity)}
          >
            <option value="starttls">STARTTLS (587)</option>
            <option value="ssl">SSL (465)</option>
            <option value="none">Ninguna</option>
          </select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="smtp-user">Usuario</Label>
          <Input
            id="smtp-user"
            autoComplete="off"
            value={form.user}
            onChange={(e) => set("user", e.target.value.trim())}
            className="h-11 md:h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="smtp-password">Contraseña</Label>
          <Input
            id="smtp-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={
              data.has_password
                ? "•••••••• (vacía para conservarla)"
                : "Contraseña o clave SMTP"
            }
            className="h-11 md:h-9"
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="smtp-sender">Remitente</Label>
          <Input
            id="smtp-sender"
            value={form.sender}
            onChange={(e) => set("sender", e.target.value)}
            placeholder="KTrain <no-reply@tudominio.com>"
            className="h-11 md:h-9"
          />
          <p className="text-xs text-muted-foreground">
            Debe ser una dirección que tu proveedor permita (con Gmail, la
            tuya).
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="public-url">URL pública de la app</Label>
          <Input
            id="public-url"
            type="url"
            required
            value={form.public_url}
            onChange={(e) => set("public_url", e.target.value.trim())}
            placeholder="https://entrenos.tudominio.com"
            className="h-11 md:h-9"
          />
          <p className="text-xs text-muted-foreground">
            Base de los enlaces de los emails (confirmar cuenta, invitaciones,
            contraseña). Si usas el túnel, pon su dirección.
          </p>
        </div>
      </div>

      <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-8">
        <input
          type="checkbox"
          className="size-4 accent-klyp-accent"
          checked={form.enabled}
          onChange={(e) => set("enabled", e.target.checked)}
        />
        Usar esta configuración (si la desactivas, se usa la del servidor)
      </label>

      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          className="min-h-11 md:min-h-9"
          disabled={save.isPending}
        >
          {save.isPending && <Loader2 className="animate-spin" />}
          Guardar
        </Button>
        <Button
          type="button"
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={test.isPending || data.mode === "disabled"}
          title={
            data.mode === "disabled"
              ? "Guarda antes la configuración"
              : undefined
          }
          onClick={() =>
            test.mutate(null, {
              onSuccess: (res) => toast.success(res.message),
              onError: (err) => toast.error(errorText(err)),
            })
          }
        >
          {test.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Send aria-hidden />
          )}
          Enviarme un email de prueba
        </Button>
      </div>
    </form>
  );
}

/** Configuración del correo (SMTP) desde el panel, sin tocar el .env. */
export function EmailTab() {
  const { data, isPending, isError, refetch } = useEmailSettings();
  if (isPending) return <Skeleton className="h-80" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar la configuración del correo."
        onRetry={() => refetch()}
      />
    );
  return (
    <div className="space-y-4">
      <StatusBanner data={data} />
      <EmailForm
        key={`${data.source}-${data.host}-${data.has_password}`}
        data={data}
      />
      <p className="text-xs text-muted-foreground">
        La contraseña se guarda cifrada y no se vuelve a mostrar. Se usa para
        confirmar cuentas nuevas, invitaciones, recuperar contraseña y avisos.
      </p>
    </div>
  );
}
