"use client";

import { Activity, Ellipsis, LogOut, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";

import {
  isActive,
  MOBILE_MORE,
  MOBILE_TABS,
  NAV_ITEMS,
  type NavItem,
  visibleFor,
} from "@/components/layout/nav";
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

function NavLinks({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1" aria-label="Principal">
      {items.map(({ href, label, icon: Icon }) => {
        const active = isActive(href, pathname);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </Link>
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

function SidebarFooter() {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <div className="mt-auto flex flex-col gap-1">
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

/** Barra de pestañas fija abajo (móvil y tablet), como una app nativa. */
function BottomNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();
  const more = visibleFor(MOBILE_MORE, !!me?.is_admin);
  const moreActive = more.some(({ href }) => isActive(href, pathname));
  return (
    <nav
      aria-label="Principal"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-sidebar-border bg-sidebar pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {MOBILE_TABS.map(({ href, label, icon: Icon }) => {
        const active = isActive(href, pathname);
        return (
          <Link
            key={href}
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
          className="flex flex-col gap-4 rounded-t-xl border-sidebar-border bg-sidebar p-4 text-sidebar-foreground pb-[calc(1rem+env(safe-area-inset-bottom))]"
        >
          <SheetTitle className="px-3 text-sidebar-foreground">Más</SheetTitle>
          <NavLinks items={more} onNavigate={() => setOpen(false)} />
          <SidebarFooter />
        </SheetContent>
      </Sheet>
    </nav>
  );
}

/** Estructura de la app: sidebar en desktop (lg+) y barra de pestañas inferior en móvil/tablet. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: me } = useMe();
  return (
    <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="hidden flex-col gap-6 bg-sidebar p-4 lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <Brand />
        <NavLinks items={visibleFor(NAV_ITEMS, !!me?.is_admin)} />
        <SidebarFooter />
      </aside>

      <header className="sticky top-0 z-20 flex h-[calc(3.5rem+env(safe-area-inset-top))] items-center bg-sidebar px-1 pt-[env(safe-area-inset-top)] lg:hidden">
        <Brand />
      </header>

      {/* Hueco inferior para que la barra de pestañas no tape el contenido. */}
      <main className="mx-auto w-full max-w-6xl p-3 pb-[calc(5rem+env(safe-area-inset-bottom))] md:p-6 md:pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:pb-6">
        {children}
      </main>

      <BottomNav />
    </div>
  );
}
