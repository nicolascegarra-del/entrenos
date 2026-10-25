"use client";

import {
  ArrowUpDown,
  Ban,
  CircleCheck,
  KeyRound,
  LayoutGrid,
  Lock,
  LogOut,
  Search,
  ShieldCheck,
  ShieldOff,
  Trash2,
  UserCheck,
  UserX,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CopyLink } from "@/components/admin/copy-link";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminModules,
  useAdminSettings,
  useAdminUserAction,
  useAdminUsers,
  useMe,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import {
  choiceValue,
  effectiveModule,
  MODULE_INFO,
  type ModuleChoice,
  moduleChoice,
  type ModuleKey,
  overridesSummary,
} from "@/lib/modules";
import { cn } from "@/lib/utils";
import type { AdminUserRow, LinkOut } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const STATUS_LABEL = {
  active: "Activo",
  unverified: "Sin confirmar email",
  pending: "Pendiente de aprobar",
  disabled: "Desactivado",
} as const;

const GARMIN_LABEL = {
  ok: "Garmin conectado",
  expired: "Garmin caducado",
  none: "Sin Garmin",
} as const;

function ActionButton({
  icon: Icon,
  children,
  onClick,
  destructive,
  disabled,
}: {
  icon: typeof Ban;
  children: React.ReactNode;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <Button
      size="sm"
      variant={destructive ? "ghost" : "outline"}
      className={
        destructive
          ? "min-h-11 text-destructive md:min-h-8"
          : "min-h-11 md:min-h-8"
      }
      onClick={onClick}
      disabled={disabled}
    >
      <Icon aria-hidden /> {children}
    </Button>
  );
}

const CHOICES: { value: ModuleChoice; label: string }[] = [
  { value: "general", label: "General" },
  { value: "on", label: "Sí" },
  { value: "off", label: "No" },
];

/** Módulos de una cuenta: seguir el valor general o fijar activado / desactivado. */
function UserModules({
  u,
  disabled,
  onChange,
}: {
  u: AdminUserRow;
  disabled: boolean;
  onChange: (key: ModuleKey, choice: ModuleChoice) => void;
}) {
  const { data: general } = useAdminModules();
  return (
    <ul className="divide-y rounded-md border bg-muted/30">
      {MODULE_INFO.map(({ key, label }) => {
        const current = moduleChoice(u.modules, key);
        const on = effectiveModule(general, u.modules, key);
        return (
          <li
            key={key}
            className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
          >
            <div className="min-w-0">
              <p id={`um-${u.id}-${key}`} className="text-sm font-medium">
                {label}
              </p>
              <p className="text-xs text-muted-foreground">
                {on ? "Activo" : "Apagado"}
                {current === "general" &&
                  general &&
                  ` · valor general (${general[key] ? "sí" : "no"})`}
              </p>
            </div>
            <div
              role="radiogroup"
              aria-labelledby={`um-${u.id}-${key}`}
              className="inline-flex rounded-md border bg-background p-0.5"
            >
              {CHOICES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  role="radio"
                  aria-checked={current === c.value}
                  disabled={disabled}
                  onClick={() => current !== c.value && onChange(key, c.value)}
                  className={cn(
                    "min-h-11 min-w-11 rounded px-2.5 text-xs font-medium transition-colors disabled:opacity-60 md:min-h-8",
                    current === c.value
                      ? "bg-klyp-navy text-white dark:bg-klyp-accent"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function UserCard({
  u,
  isMe,
  emailEnabled,
}: {
  u: AdminUserRow;
  isMe: boolean;
  emailEnabled: boolean;
}) {
  const action = useAdminUserAction();
  const [link, setLink] = useState<LinkOut | null>(null);
  const [showModules, setShowModules] = useState(false);
  const summary = overridesSummary(u.modules);

  const run = (
    path: string,
    ok: string,
    opts: { method?: string; body?: unknown; confirm?: string } = {},
  ) => {
    if (opts.confirm && !window.confirm(opts.confirm)) return;
    action.mutate(
      { path, method: opts.method, body: opts.body },
      {
        onSuccess: (data) => {
          if (path.endsWith("/reset-link")) setLink(data as LinkOut);
          toast.success(ok);
        },
        onError: (err) => toast.error(errorText(err)),
      },
    );
  };

  const resetLink = () => {
    const sendEmail =
      emailEnabled &&
      window.confirm(
        `¿Enviar también el enlace por email a ${u.email}? (Cancelar = solo generarlo para copiarlo)`,
      );
    run(`${u.id}/reset-link`, "Enlace generado.", {
      body: { send_email: sendEmail },
    });
  };

  const remove = () => {
    const typed = window.prompt(
      `Se borrarán la cuenta de ${u.email} y TODOS sus datos. No se puede deshacer.\n\nEscribe su email para confirmar:`,
    );
    if (typed == null) return;
    run(`${u.id}?confirm=${encodeURIComponent(typed)}`, "Usuario borrado.", {
      method: "DELETE",
    });
  };

  return (
    <li className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 truncate font-medium">{u.email}</span>
        {isMe && <Badge variant="outline">Tú</Badge>}
        {u.is_admin && (
          <Badge>
            <ShieldCheck aria-hidden /> Admin
          </Badge>
        )}
        <Badge
          variant={
            u.status === "active"
              ? "secondary"
              : u.status === "pending"
                ? "default"
                : "destructive"
          }
        >
          {STATUS_LABEL[u.status]}
        </Badge>
        <Badge variant="outline">
          {u.tier === "basic" ? "Básica" : "Completa"}
        </Badge>
        {u.inactivity_warned_at && (
          <Badge variant="destructive">Avisada por inactividad</Badge>
        )}
        {u.locked && (
          <Badge variant="destructive">
            <Lock aria-hidden /> Bloqueado
          </Badge>
        )}
        {summary && <Badge variant="outline">{summary}</Badge>}
      </div>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3 lg:grid-cols-6">
        <li>
          <span>Alta {formatDate(u.created_at)}</span>
        </li>
        <li>
          <span>
            Acceso {u.last_login_at ? formatDateTime(u.last_login_at) : "nunca"}
          </span>
        </li>
        <li>
          <span className={u.garmin === "expired" ? "text-destructive" : ""}>
            {GARMIN_LABEL[u.garmin]}
          </span>
        </li>
        <li>
          <span
            className={
              u.last_sync?.status === "error" ? "text-destructive" : ""
            }
            title={u.last_sync?.error ?? undefined}
          >
            Sync{" "}
            {u.last_sync
              ? `${formatDateTime(u.last_sync.at)}${u.last_sync.status === "error" ? " (error)" : ""}`
              : "nunca"}
          </span>
        </li>
        <li>
          <span>{formatNumber(u.activities)} actividades</span>
        </li>
        <li>
          <span>
            IA 30 d: {u.ai_questions_30d} preguntas
            {u.ai_tokens_30d > 0 &&
              ` · ${formatNumber(u.ai_tokens_30d / 1000, 1)} k tokens`}
          </span>
        </li>
      </ul>

      <div className="flex flex-wrap gap-2">
        {u.status === "pending" ? (
          <>
            <ActionButton
              icon={UserCheck}
              onClick={() => run(`${u.id}/approve`, "Solicitud aprobada.")}
            >
              Aprobar
            </ActionButton>
            <ActionButton
              icon={UserX}
              destructive
              onClick={() =>
                run(`${u.id}/reject`, "Solicitud rechazada.", {
                  confirm: `¿Rechazar la solicitud de ${u.email}? Se borrará.`,
                })
              }
            >
              Rechazar
            </ActionButton>
          </>
        ) : (
          <>
            <ActionButton
              icon={u.is_admin ? ShieldOff : ShieldCheck}
              disabled={action.isPending}
              onClick={() =>
                run(
                  `${u.id}`,
                  u.is_admin
                    ? "Ya no es administrador."
                    : "Ahora es administrador.",
                  {
                    method: "PATCH",
                    body: { is_admin: !u.is_admin },
                    confirm: u.is_admin
                      ? `¿Quitar los permisos de administrador a ${u.email}?`
                      : `¿Hacer administrador a ${u.email}? Podrá gestionar usuarios e invitaciones.`,
                  },
                )
              }
            >
              {u.is_admin ? "Quitar admin" : "Hacer admin"}
            </ActionButton>
            {!isMe && (
              <ActionButton
                icon={u.status === "active" ? Ban : CircleCheck}
                onClick={() =>
                  run(
                    `${u.id}`,
                    u.status === "active"
                      ? "Usuario desactivado."
                      : "Usuario activado.",
                    {
                      method: "PATCH",
                      body: {
                        status: u.status === "active" ? "disabled" : "active",
                      },
                      confirm:
                        u.status === "active"
                          ? `¿Desactivar a ${u.email}? No podrá entrar ni sincronizar hasta que lo actives.`
                          : undefined,
                    },
                  )
                }
              >
                {u.status === "active" ? "Desactivar" : "Activar"}
              </ActionButton>
            )}
            <ActionButton
              icon={ArrowUpDown}
              onClick={() =>
                run(
                  `${u.id}`,
                  u.tier === "basic"
                    ? "Ahora tiene cuenta Completa."
                    : "Ahora tiene cuenta Básica.",
                  {
                    method: "PATCH",
                    body: { tier: u.tier === "basic" ? "full" : "basic" },
                  },
                )
              }
            >
              {u.tier === "basic" ? "Pasar a Completa" : "Pasar a Básica"}
            </ActionButton>
            <ActionButton
              icon={LayoutGrid}
              onClick={() => setShowModules((v) => !v)}
            >
              {showModules ? "Ocultar módulos" : "Módulos"}
            </ActionButton>
            {u.status === "active" && (
              <ActionButton icon={KeyRound} onClick={resetLink}>
                Enlace de contraseña
              </ActionButton>
            )}
            {u.locked && (
              <ActionButton
                icon={Lock}
                onClick={() => run(`${u.id}/unlock`, "Desbloqueado.")}
              >
                Desbloquear
              </ActionButton>
            )}
            <ActionButton
              icon={LogOut}
              onClick={() =>
                run(`${u.id}/logout`, "Sesiones cerradas.", {
                  confirm: `¿Cerrar todas las sesiones de ${u.email}?`,
                })
              }
            >
              Cerrar sesiones
            </ActionButton>
            {!isMe && (
              <ActionButton icon={Trash2} destructive onClick={remove}>
                Borrar
              </ActionButton>
            )}
          </>
        )}
      </div>
      {showModules && u.status !== "pending" && (
        <UserModules
          u={u}
          disabled={action.isPending}
          onChange={(key, choice) =>
            run(
              `${u.id}`,
              `${MODULE_INFO.find((m) => m.key === key)?.label}: ${
                choice === "general"
                  ? "vuelve al valor general"
                  : choice === "on"
                    ? "activado para esta cuenta"
                    : "desactivado para esta cuenta"
              }.`,
              {
                method: "PATCH",
                body: { modules: { [key]: choiceValue(choice) } },
              },
            )
          }
        />
      )}
      {link && (
        <CopyLink
          link={link.link}
          expiresAt={link.expires_at}
          emailed={link.emailed}
          onClose={() => setLink(null)}
        />
      )}
    </li>
  );
}

/** Usuarios: buscar, permisos de administrador, estado, sesiones y borrado. */
export function UsersTab() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const { data, isPending, isError, refetch } = useAdminUsers(query);
  const { data: me } = useMe();
  const { data: settings } = useAdminSettings();

  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <label htmlFor="buscar-usuario" className="sr-only">
          Buscar por email
        </label>
        <Input
          id="buscar-usuario"
          type="search"
          placeholder="Buscar por email…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            if (!e.target.value) setQuery("");
          }}
          className="h-11 md:h-9"
        />
        <Button type="submit" variant="outline" className="min-h-11 md:min-h-9">
          <Search aria-hidden /> Buscar
        </Button>
      </form>
      {isPending ? (
        <Skeleton className="h-40" />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar los usuarios."
          onRetry={() => refetch()}
        />
      ) : !data.items.length ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No hay usuarios{query ? " con ese email" : ""}.
        </p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {data.total} usuario{data.total === 1 ? "" : "s"}
          </p>
          <ul className="space-y-2">
            {data.items.map((u) => (
              <UserCard
                key={u.id}
                u={u}
                isMe={u.id === me?.id}
                emailEnabled={!!settings?.email_enabled}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
