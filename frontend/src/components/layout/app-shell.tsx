"use client";

import { Activity, LogOut, Menu, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";

import { NAV_ITEMS } from "@/components/layout/nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { logout } from "@/lib/api";
import { cn } from "@/lib/utils";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1" aria-label="Principal">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
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

/** Estructura de la app: sidebar en desktop (lg+) y menú hamburguesa en móvil/tablet. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="hidden flex-col gap-6 bg-sidebar p-4 lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <Brand />
        <NavLinks />
        <SidebarFooter />
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 bg-sidebar px-3 lg:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-11 text-sidebar-foreground"
              aria-label="Abrir menú"
            >
              <Menu className="size-6" />
            </Button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="flex w-72 flex-col gap-6 border-sidebar-border bg-sidebar p-4"
          >
            <SheetTitle className="sr-only">Menú</SheetTitle>
            <Brand />
            <NavLinks onNavigate={() => setOpen(false)} />
            <SidebarFooter />
          </SheetContent>
        </Sheet>
        <Brand />
      </header>

      <main className="mx-auto w-full max-w-6xl p-3 md:p-6">{children}</main>
    </div>
  );
}
