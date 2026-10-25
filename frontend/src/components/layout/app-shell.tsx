"use client";

import { LogOut, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";

import { Logo, LogoMark } from "@/components/brand/logo";
import {
  accountFor,
  currentLocation,
  isUnder,
  screenTitle,
  SECTIONS,
  type Section,
} from "@/components/layout/nav";
import { SectionTabs } from "@/components/layout/section-tabs";
import { SyncButton } from "@/components/layout/sync-button";
import { TourButton } from "@/components/tour/tour-button";
import { TourProvider } from "@/components/tour/tour-provider";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useCoachBadge, useGarminStatus, useMe } from "@/hooks/use-api";
import { logout } from "@/lib/api";
import { cn } from "@/lib/utils";

const linkClass = (active: boolean) =>
  cn(
    "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
    active
      ? "bg-sidebar-accent text-sidebar-accent-foreground"
      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
  );

/** Punto de aviso (entrenador con algo pendiente, reloj desconectado…). */
function Dot({ className, label }: { className?: string; label: string }) {
  return (
    <span
      role="status"
      aria-label={label}
      className={cn(
        "size-2.5 rounded-full bg-klyp-accent ring-2 ring-sidebar",
        className,
      )}
    />
  );
}

/** Grupos del menú de cuenta (Cuenta, Ayuda) con su título. */
function AccountLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: me } = useMe();
  return (
    <div className="flex flex-col gap-3">
      {accountFor(!!me?.is_admin).map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <p className="px-3 text-xs font-semibold tracking-wide text-sidebar-foreground/50 uppercase">
            {group.title}
          </p>
          {group.items.map(({ href, label, icon: Icon }) => {
            const active = isUnder(href, pathname);
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={linkClass(active)}
              >
                <Icon className="size-5" aria-hidden />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function initial(email?: string) {
  return (email?.trim()[0] ?? "?").toUpperCase();
}

function Avatar({ email }: { email?: string }) {
  return (
    <span
      aria-hidden
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-klyp-accent text-sm font-semibold text-white"
    >
      {initial(email)}
    </span>
  );
}

/** ¿Hay algo que revisar en Ajustes? (por ahora, el reloj desconectado). */
function useSettingsWarning() {
  const { data } = useGarminStatus();
  return data?.connection.status === "expired";
}

/** Bloque de cuenta: quién eres, Ajustes, Ayuda, tema y cerrar sesión. */
function AccountPanel({ onNavigate }: { onNavigate?: () => void }) {
  const { data: me } = useMe();
  return (
    <div className="flex flex-col gap-3">
      {me && (
        <div className="flex min-w-0 items-center gap-3 px-3">
          <Avatar email={me.email} />
          <span className="truncate text-sm text-sidebar-foreground/80">
            {me.email}
          </span>
        </div>
      )}
      <AccountLinks onNavigate={onNavigate} />
      <div className="border-t border-sidebar-border pt-3">
        <SessionActions />
      </div>
    </div>
  );
}

/** Avatar de la cabecera del móvil: abre el menú de cuenta. */
function AccountMenu() {
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();
  const warn = useSettingsWarning();
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          data-tour="account"
          aria-label={
            warn
              ? "Tu cuenta y ajustes (hay algo que revisar)"
              : "Tu cuenta y ajustes"
          }
          className="relative flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-sidebar-accent/60"
        >
          <Avatar email={me?.email} />
          {warn && (
            <span
              aria-hidden
              className="absolute top-1.5 right-1.5 size-2.5 rounded-full bg-amber-400 ring-2 ring-sidebar"
            />
          )}
        </button>
      </SheetTrigger>
      <SheetContent
        side="bottom"
        className="flex max-h-[85dvh] flex-col gap-4 overflow-y-auto rounded-t-xl border-sidebar-border bg-sidebar p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] text-sidebar-foreground"
      >
        <SheetTitle className="px-3 text-sidebar-foreground">
          Tu cuenta
        </SheetTitle>
        <AccountPanel onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}

/** Sidebar de escritorio: las secciones con sus subsecciones (la actual, desplegada). */
function SidebarNav() {
  const pathname = usePathname();
  const { section: current, sub } = currentLocation(pathname);
  const coachBadge = useCoachBadge();
  return (
    <nav className="flex flex-col gap-1" aria-label="Principal" data-tour="nav">
      {SECTIONS.map((section) => {
        const Icon = section.icon;
        const active = current?.key === section.key;
        return (
          <div key={section.key}>
            <Link
              href={section.href}
              data-tour={`tab-${section.key}`}
              aria-current={
                active && !section.children.length ? "page" : undefined
              }
              className={linkClass(active && !section.children.length)}
            >
              <Icon
                className={cn("size-5", active && "text-klyp-accent")}
                aria-hidden
              />
              {section.label}
              {section.key === "entrenador" && coachBadge && (
                <Dot
                  className="ml-auto"
                  label="Entrenador: tienes algo pendiente"
                />
              )}
            </Link>
            {active && section.children.length > 0 && (
              <ul
                data-tour="section-tabs"
                className="mt-1 mb-2 ml-5 flex flex-col gap-0.5 border-l border-sidebar-border pl-3"
              >
                {section.children.map((c) => {
                  const on = c.href === sub?.href;
                  return (
                    <li key={c.href}>
                      <Link
                        href={c.href}
                        aria-current={on ? "page" : undefined}
                        className={cn(linkClass(on), "min-h-9")}
                      >
                        {c.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}

function Brand() {
  return <Logo className="px-3 text-xl text-sidebar-foreground" onDark />;
}

function SessionActions() {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <div className="flex flex-col gap-1">
      <Button
        variant="ghost"
        className="min-h-11 justify-start gap-3 text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      >
        {resolvedTheme === "dark" ? (
          <Sun className="size-5" />
        ) : (
          <Moon className="size-5" />
        )}
        Tema {resolvedTheme === "dark" ? "claro" : "oscuro"}
      </Button>
      <Button
        variant="ghost"
        className="min-h-11 justify-start gap-3 text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        onClick={async () => {
          await logout();
          router.replace("/login");
        }}
      >
        <LogOut className="size-5" />
        Cerrar sesión
      </Button>
    </div>
  );
}

const tabClass = (active: boolean) =>
  cn(
    "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors",
    active
      ? "text-sidebar-foreground"
      : "text-sidebar-foreground/60 hover:text-sidebar-foreground",
  );

/** Pestaña central del entrenador: botón redondo destacado, con aviso si tiene algo para ti. */
function CoachTab({ section, active }: { section: Section; active: boolean }) {
  const badge = useCoachBadge();
  const Icon = section.icon;
  return (
    <Link
      href={section.href}
      data-tour={`tab-${section.key}`}
      aria-current={active ? "page" : undefined}
      aria-label={
        badge ? `${section.label}: tienes algo pendiente` : section.label
      }
      className={tabClass(active)}
    >
      <span
        className={cn(
          "relative -mt-4 flex size-11 items-center justify-center rounded-full bg-klyp-accent text-white shadow-md ring-4 ring-sidebar transition-transform",
          active && "scale-105",
        )}
      >
        <Icon className="size-5" aria-hidden />
        {badge && (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 size-3 rounded-full bg-amber-400 ring-2 ring-sidebar"
          />
        )}
      </span>
      {section.label}
    </Link>
  );
}

/** Barra de pestañas fija abajo (móvil y tablet): Hoy, Entrenos, Entrenador, Plan y Progreso. */
function BottomNav() {
  const pathname = usePathname();
  const { section } = currentLocation(pathname);
  return (
    <nav
      aria-label="Principal"
      data-tour="nav"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-sidebar-border bg-sidebar pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {SECTIONS.map((s) => {
        const active = section?.key === s.key;
        if (s.key === "entrenador")
          return <CoachTab key={s.key} section={s} active={active} />;
        const Icon = s.icon;
        return (
          <Link
            key={s.key}
            href={s.href}
            data-tour={`tab-${s.key}`}
            aria-current={active ? "page" : undefined}
            className={tabClass(active)}
          >
            <Icon
              className={cn("size-5", active && "text-klyp-accent")}
              aria-hidden
            />
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Estructura de la app: sidebar por secciones en escritorio (lg+) y barra inferior + cabecera en móvil. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <TourProvider>
      <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[16rem_1fr]">
        <aside className="hidden flex-col gap-5 overflow-y-auto bg-sidebar p-4 lg:sticky lg:top-0 lg:flex lg:h-dvh">
          <div className="flex items-center justify-between gap-1">
            <Brand />
          </div>
          <div className="px-1 text-sidebar-foreground">
            <SyncButton />
          </div>
          <SidebarNav />
          <div
            className="mt-auto border-t border-sidebar-border pt-4"
            data-tour="account"
          >
            <AccountPanel />
          </div>
        </aside>

        {/* Cabecera móvil: dónde estás, ayuda, sincronizar y tu cuenta, siempre a mano. */}
        <header className="sticky top-0 z-20 flex h-[calc(3.5rem+env(safe-area-inset-top))] items-center justify-between gap-2 bg-sidebar px-3 pt-[env(safe-area-inset-top)] text-sidebar-foreground lg:hidden">
          <div className="flex min-w-0 items-center gap-2 font-heading text-lg font-semibold">
            <LogoMark className="size-6" />
            <span className="truncate">{screenTitle(pathname)}</span>
          </div>
          <div className="flex shrink-0 items-center">
            <TourButton className="text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground" />
            <SyncButton />
            <AccountMenu />
          </div>
        </header>

        {/* Hueco inferior para que la barra de pestañas no tape el contenido. */}
        <main className="mx-auto w-full max-w-6xl p-3 pb-[calc(5rem+env(safe-area-inset-bottom))] md:p-6 md:pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:pb-6">
          <SectionTabs />
          {children}
        </main>

        <BottomNav />
      </div>
    </TourProvider>
  );
}
