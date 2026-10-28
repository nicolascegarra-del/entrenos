"use client";

import {
  Bell,
  ChevronRight,
  Link2,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageHeader } from "@/components/layout/page-header";
import {
  useAiProviders,
  useGarminStatus,
  useMe,
  useModules,
  useNotifications,
  useSources,
} from "@/hooks/use-api";
import { filterByModule, type ModuleKey } from "@/lib/modules";
import { settingsStatus, type SettingsKey } from "@/lib/settings-sections";
import { cn } from "@/lib/utils";

const SECTIONS: {
  key: SettingsKey;
  label: string;
  icon: LucideIcon;
  hint: string;
  module?: ModuleKey;
}[] = [
  {
    key: "perfil",
    label: "Perfil",
    icon: UserRound,
    hint: "Edad, peso y altura",
  },
  {
    key: "conexiones",
    label: "Conexiones",
    icon: Link2,
    hint: "Tu reloj: Garmin, Apple Watch, COROS…",
  },
  {
    key: "notificaciones",
    label: "Notificaciones",
    icon: Bell,
    hint: "Avisos en el móvil",
  },
  {
    key: "asistente",
    label: "Asistente IA",
    icon: Sparkles,
    hint: "Tu clave y el modelo",
    module: "ia",
  },
  {
    key: "cuenta",
    label: "Cuenta y privacidad",
    icon: ShieldCheck,
    hint: "Contraseña y tus datos",
  },
];

/** Ajustes como lista de secciones con su estado (como en una app de móvil). */
export default function AjustesPage() {
  const router = useRouter();
  // Oura vuelve a /ajustes?oura=ok|error: su tarjeta (y el aviso) está en Conexiones.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("oura"))
      router.replace(`/ajustes/conexiones?${params.toString()}#reloj-oura`);
  }, [router]);
  const { data: garmin } = useGarminStatus();
  const { data: ai } = useAiProviders();
  const { data: notifications } = useNotifications();
  const { data: me } = useMe();
  const { data: sources } = useSources();
  const { data: modules } = useModules();
  const status = settingsStatus({ garmin, ai, notifications, me, sources });
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title="Ajustes" hideTitleOnMobile />
      <ul
        data-tour="settings-list"
        className="divide-y overflow-hidden rounded-lg border bg-card shadow-sm"
      >
        {filterByModule(SECTIONS, modules).map(
          ({ key, label, icon: Icon, hint }) => {
            const st = status[key];
            return (
              <li key={key}>
                <Link
                  href={`/ajustes/${key}`}
                  className="flex min-h-14 items-center gap-3 px-4 py-3 hover:bg-muted/60"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Icon className="size-5 text-klyp-accent" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{label}</span>
                    <span
                      className={cn(
                        "flex items-center gap-1 text-xs",
                        st?.warn
                          ? "text-amber-700 dark:text-amber-300"
                          : "text-muted-foreground",
                      )}
                    >
                      {st?.warn && (
                        <TriangleAlert
                          className="size-3.5 shrink-0"
                          aria-hidden
                        />
                      )}
                      <span className="truncate">{st?.text ?? hint}</span>
                    </span>
                  </span>
                  <ChevronRight
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                </Link>
              </li>
            );
          },
        )}
      </ul>
    </section>
  );
}
