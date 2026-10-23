"use client";

import { Activity, Ellipsis, LogOut, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";

import {
  currentLocation,
  isUnder,
  moreFor,
  screenTitle,
  SECTIONS,
} from "@/components/layout/nav";
import { SectionTabs } from "@/components/layout/section-tabs";
import { SyncButton } from "@/components/layout/sync-button";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useMe } from "@/hooks/use-api";
import { logout } from "@/lib/api";
import { cn } from "@/lib/utils";

const linkClass = (active: boolean) =>
  cn(
    "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
    active
      ? "bg-sidebar-accent text-sidebar-accent-foreground"
      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
  );

/** Grupos del «Más» (Asistente, Cuenta, Ayuda) con su título. */
function MoreLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: me } = useMe();
  return (
    <div className="flex flex-col gap-3">
      {moreFor(!!me?.is_admin).map((group) => (
        <div key={group.title ?? "principal"} className="flex flex-col gap-1">
          {group.title && (
            <p className="px-3 text-xs font-semibold tracking-wide text-sidebar-foreground/50 uppercase">
              {group.title}
            </p>
          )}
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

/** Sidebar de escritorio: las 4 secciones con sus subsecciones (la actual, desplegada). */
function SidebarNav() {
  const pathname = usePathname();
  const { section: current, sub } = currentLocation(pathname);
  return (
    <nav className="flex flex-col gap-1" aria-label="Principal">
      {SECTIONS.map((section) => {
        const Icon = section.icon;
        const active = current?.key === section.key;
        return (
          <div key={section.key}>
            <Link
              href={section.href}
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
            </Link>
            {active && section.children.length > 0 && (
              <ul className="mt-1 mb-2 ml-5 flex flex-col gap-0.5 border-l border-sidebar-border pl-3">
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
  return (
    <div className="flex items-center gap-2 px-3 font-heading text-lg font-semibold text-sidebar-foreground">
      <Activity className="size-6 text-klyp-accent" aria-hidden />
      APP ENTRENOS
    </div>
  );
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

/** Barra de pestañas fija abajo (móvil y tablet): Hoy, Entrenos, Plan, Progreso y Más. */
function BottomNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { section } = currentLocation(pathname);
  const moreActive = section === null;
  return (
    <nav
      aria-label="Principal"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-sidebar-border bg-sidebar pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {SECTIONS.map(({ key, href, label, icon: Icon }) => {
        const active = section?.key === key;
        return (
          <Link
            key={key}
            href={href}
            aria-current={active ? "page" : undefined}
            className={tabClass(active)}
          >
            <Icon
              className={cn("size-5", active && "text-klyp-accent")}
              aria-hidden
            />
            {label}
          </Link>
        );
      })}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button
            type="button"
            className={tabClass(moreActive)}
            aria-current={moreActive ? "page" : undefined}
          >
            <Ellipsis
              className={cn("size-5", moreActive && "text-klyp-accent")}
              aria-hidden
            />
            Más
          </button>
        </SheetTrigger>
        <SheetContent
          side="bottom"
          className="flex max-h-[85dvh] flex-col gap-4 overflow-y-auto rounded-t-xl border-sidebar-border bg-sidebar p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] text-sidebar-foreground"
        >
          <SheetTitle className="px-3 text-sidebar-foreground">Más</SheetTitle>
          <MoreLinks onNavigate={() => setOpen(false)} />
          <div className="border-t border-sidebar-border pt-3">
            <SessionActions />
          </div>
        </SheetContent>
      </Sheet>
    </nav>
  );
}

/** Estructura de la app: sidebar por secciones en escritorio (lg+) y barra inferior + cabecera en móvil. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="hidden flex-col gap-5 overflow-y-auto bg-sidebar p-4 lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <div className="flex items-center justify-between gap-1">
          <Brand />
        </div>
        <div className="px-1 text-sidebar-foreground">
          <SyncButton />
        </div>
        <SidebarNav />
        <div className="border-t border-sidebar-border pt-4">
          <MoreLinks />
        </div>
        <div className="mt-auto">
          <SessionActions />
        </div>
      </aside>

      {/* Cabecera móvil: dónde estás y sincronizar, siempre a mano. */}
      <header className="sticky top-0 z-20 flex h-[calc(3.5rem+env(safe-area-inset-top))] items-center justify-between gap-2 bg-sidebar px-3 pt-[env(safe-area-inset-top)] text-sidebar-foreground lg:hidden">
        <div className="flex min-w-0 items-center gap-2 font-heading text-lg font-semibold">
          <Activity className="size-5 shrink-0 text-klyp-accent" aria-hidden />
          <span className="truncate">{screenTitle(pathname)}</span>
        </div>
        <SyncButton />
      </header>

      {/* Hueco inferior para que la barra de pestañas no tape el contenido. */}
      <main className="mx-auto w-full max-w-6xl p-3 pb-[calc(5rem+env(safe-area-inset-bottom))] md:p-6 md:pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:pb-6">
        <SectionTabs />
        {children}
      </main>

      <BottomNav />
    </div>
  );
}
