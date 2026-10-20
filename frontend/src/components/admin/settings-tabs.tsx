"use client";

import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  DatabaseBackup,
  Mail,
  RefreshCw,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminAudit,
  useAdminSettings,
  useAdminSystem,
  useSaveAdminSettings,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RegistrationMode } from "@/types/api";

const MODES: { value: RegistrationMode; label: string; help: string }[] = [
  {
    value: "invite",
    label: "Solo con invitación",
    help: "Nadie puede crear una cuenta sin un enlace de invitación tuyo. La opción más segura.",
  },
  {
    value: "approval",
    label: "Con aprobación",
    help: "Cualquiera puede pedir una cuenta desde el login; entra cuando la apruebas en Usuarios.",
  },
  {
    value: "open",
    label: "Abierto",
    help: "Cualquiera con el enlace de la app puede crear su cuenta al momento.",
  },
];

/** Modo de registro de la app. */
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
              save.mutate(m.value, {
                onSuccess: () => toast.success(`Registro: ${m.label}.`),
                onError: (err) =>
                  toast.error(
                    err instanceof ApiError
                      ? err.message
                      : "No se pudo guardar.",
                  ),
              })
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
  );
}

function StatusLine({
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

function Panel({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Mail;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2 rounded-lg border p-3">
      <h3 className="flex items-center gap-2 font-medium">
        <Icon className="size-4 text-klyp-accent" aria-hidden /> {title}
      </h3>
      {children}
    </section>
  );
}

const EMAIL_MODE = {
  smtp: "Envío por SMTP activo.",
  file: "Modo de prueba: los emails se guardan en una carpeta del servidor.",
  disabled:
    "Sin correo: los enlaces de invitación y contraseña hay que copiarlos y enviarlos a mano.",
} as const;

/** Estado del sistema: sincronizador, Garmin, copias de seguridad y correo. */
export function SystemTab() {
  const { data, isPending, isError, refetch, isFetching } = useAdminSystem();
  if (isPending) return <Skeleton className="h-60" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar el estado del sistema."
        onRetry={() => refetch()}
      />
    );
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => refetch()}
        className="inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-klyp-accent md:min-h-8"
      >
        <RefreshCw
          className={cn("size-4", isFetching && "animate-spin")}
          aria-hidden
        />
        Actualizar
      </button>
      <div className="grid gap-3 md:grid-cols-2">
        <Panel icon={RefreshCw} title="Sincronizador de Garmin">
          <StatusLine ok={data.worker_ok}>
            {data.worker_ok == null
              ? "Aún sin latido: si acabas de arrancar la app, espera un minuto; si sigue así, el worker o beat no funcionan."
              : data.worker_ok
                ? "Funcionando."
                : "Parado: el worker o beat no responden."}
            {data.last_heartbeat &&
              ` Último latido: ${formatDateTime(data.last_heartbeat)}.`}
          </StatusLine>
          <p className="text-sm text-muted-foreground">
            Última sincronización:{" "}
            {data.last_sync_at ? formatDateTime(data.last_sync_at) : "ninguna"}
          </p>
        </Panel>

        <Panel icon={CircleAlert} title="Problemas con Garmin">
          {!data.garmin_expired.length && !data.sync_failing.length ? (
            <StatusLine ok>Sin problemas.</StatusLine>
          ) : (
            <ul className="space-y-1 text-sm">
              {data.garmin_expired.map((email) => (
                <li key={`exp-${email}`} className="text-destructive">
                  {email}: conexión caducada, debe reconectar en Ajustes.
                </li>
              ))}
              {data.sync_failing.map((f) => (
                <li key={`err-${f.email}`} className="text-destructive">
                  {f.email}: falló la sincronización del {formatDateTime(f.at)}
                  {f.error ? ` (${f.error})` : ""}.
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel icon={DatabaseBackup} title="Copias de seguridad">
          {data.last_backup ? (
            <StatusLine
              ok={
                Date.now() - new Date(data.last_backup.at).getTime() <
                2 * 86_400_000
              }
            >
              Última: {formatDateTime(data.last_backup.at)} (
              {formatNumber(data.last_backup.size_mb, 1)} MB) ·{" "}
              {data.last_backup.count} guardadas.
            </StatusLine>
          ) : (
            <StatusLine ok={null}>
              No hay copias visibles (en local no se hacen; en producción las
              hace el servicio de copias diarias).
            </StatusLine>
          )}
        </Panel>

        <Panel icon={Mail} title="Correo">
          <StatusLine ok={data.email_mode === "smtp" ? true : null}>
            {EMAIL_MODE[data.email_mode]}
          </StatusLine>
        </Panel>

        <Panel icon={Users} title="Usuarios">
          <p className="text-sm">
            {data.users_by_status.active ?? 0} activos ·{" "}
            {data.users_by_status.disabled ?? 0} desactivados ·{" "}
            {data.pending_requests} pendientes de aprobar
          </p>
        </Panel>
      </div>
    </div>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "user.admin_granted": "Hizo administrador a",
  "user.admin_revoked": "Quitó los permisos de administrador a",
  "user.enabled": "Activó a",
  "user.disabled": "Desactivó a",
  "user.approved": "Aprobó la solicitud de",
  "user.rejected": "Rechazó la solicitud de",
  "user.sessions_revoked": "Cerró las sesiones de",
  "user.unlocked": "Desbloqueó a",
  "user.reset_link": "Generó un enlace de contraseña para",
  "user.deleted": "Borró la cuenta de",
  "account.self_deleted": "Borró su propia cuenta",
  "invitation.created": "Invitó a",
  "invitation.renewed": "Renovó la invitación de",
  "invitation.deleted": "Anuló la invitación de",
  "settings.registration_mode": "Cambió el modo de registro",
};

const MODE_LABEL: Record<string, string> = {
  invite: "solo con invitación",
  approval: "con aprobación",
  open: "abierto",
};

/** Registro de acciones de administración. */
export function AuditTab() {
  const { data, isPending, isError, refetch } = useAdminAudit();
  if (isPending) return <Skeleton className="h-40" />;
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar la actividad."
        onRetry={() => refetch()}
      />
    );
  if (!data.length)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Aún no hay acciones registradas.
      </p>
    );
  return (
    <ul className="divide-y rounded-lg border text-sm">
      {data.map((a) => {
        const target =
          a.action === "settings.registration_mode"
            ? `a «${MODE_LABEL[String(a.detail.after)] ?? a.detail.after}»`
            : a.action === "account.self_deleted"
              ? ""
              : (a.target_email ?? String(a.detail.email ?? ""));
        return (
          <li key={a.id} className="flex flex-wrap gap-x-2 p-3">
            <span className="text-muted-foreground tabular-nums">
              {formatDateTime(a.created_at)}
            </span>
            <span>
              <strong>{a.actor_email ?? "Usuario borrado"}</strong>{" "}
              {(ACTION_LABEL[a.action] ?? a.action).toLowerCase()} {target}
              {a.detail.emailed === true && " (por email)"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
