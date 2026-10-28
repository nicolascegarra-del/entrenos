"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ConnectionsTab } from "@/components/admin/connections-tab";
import { EmailTab } from "@/components/admin/email-tab";
import { InvitationsTab } from "@/components/admin/invitations-tab";
import { ModulesTab } from "@/components/admin/modules-tab";
import { RegistrationTab } from "@/components/admin/registration-tab";
import { AuditTab, SystemTab } from "@/components/admin/settings-tabs";
import { UsersTab } from "@/components/admin/users-tab";
import { EmptyState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminSystem, useMe } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "users", label: "Usuarios", Panel: UsersTab },
  { key: "invitations", label: "Invitaciones", Panel: InvitationsTab },
  { key: "registration", label: "Registro", Panel: RegistrationTab },
  { key: "email", label: "Correo", Panel: EmailTab },
  { key: "modules", label: "Módulos", Panel: ModulesTab },
  { key: "connections", label: "Conexiones", Panel: ConnectionsTab },
  { key: "system", label: "Sistema", Panel: SystemTab },
  { key: "audit", label: "Actividad", Panel: AuditTab },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function AdminPanel() {
  const [tab, setTab] = useState<TabKey>("users");
  const { data: system } = useAdminSystem();
  const { Panel } = TABS.find((t) => t.key === tab)!;
  return (
    <>
      <div
        role="tablist"
        aria-label="Secciones de administración"
        className="-mx-3 flex gap-1 overflow-x-auto px-3 md:mx-0 md:px-0"
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            onClick={() => setTab(t.key)}
            className={cn(
              "min-h-11 shrink-0 rounded-md px-3 text-sm font-medium transition-colors md:min-h-9",
              tab === t.key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {t.label}
            {t.key === "users" && !!system?.pending_requests && (
              <span className="ml-1.5 rounded-full bg-klyp-accent px-1.5 text-xs text-white">
                {system.pending_requests}
              </span>
            )}
            {t.key === "system" &&
              system &&
              (system.worker_ok === false ||
                system.garmin_expired.length > 0 ||
                system.sync_failing.length > 0) && (
                <span
                  className="ml-1.5 inline-block size-2 rounded-full bg-destructive"
                  aria-label="Hay avisos"
                />
              )}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="rounded-lg border bg-card p-3 shadow-sm md:p-4"
      >
        <Panel />
      </div>
    </>
  );
}

/** Panel de administración (solo administradores). */
export default function AdminPage() {
  const { data: me, isPending } = useMe();
  return (
    <section className="space-y-3 md:space-y-4">
      <h1 className="flex items-center gap-2 font-heading text-2xl font-bold md:text-3xl">
        <ShieldCheck className="size-6 text-klyp-accent" aria-hidden />
        Administración
      </h1>
      {isPending ? (
        <Skeleton className="h-64" />
      ) : !me?.is_admin ? (
        <EmptyState icon={ShieldCheck} title="Solo para administradores">
          <p className="text-sm text-muted-foreground">
            Pide a un administrador que te dé permisos si los necesitas.
          </p>
        </EmptyState>
      ) : (
        <AdminPanel />
      )}
    </section>
  );
}
