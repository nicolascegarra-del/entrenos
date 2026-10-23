"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { atSubSectionRoot, currentLocation } from "@/components/layout/nav";
import { cn } from "@/lib/utils";

/**
 * Pestañas de la sección actual (p. ej. Actividades · Recorridos · Material). Solo en la portada de cada
 * subsección: en un detalle (una actividad concreta) estorban y se usa la flecha de volver.
 * En escritorio no hacen falta: el sidebar ya muestra las subsecciones.
 */
export function SectionTabs() {
  const pathname = usePathname();
  const { section, sub } = currentLocation(pathname);
  if (!section || section.children.length < 2 || !atSubSectionRoot(pathname))
    return null;
  return (
    <nav
      aria-label={`Secciones de ${section.label}`}
      className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-10 -mx-3 mb-3 border-b bg-background/95 px-3 backdrop-blur md:-mx-6 md:px-6 lg:hidden"
    >
      <ul className="flex gap-1 overflow-x-auto [scrollbar-width:none]">
        {section.children.map((c) => {
          const active = c.href === sub?.href;
          return (
            <li key={c.href} className="min-w-max flex-1">
              <Link
                href={c.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center justify-center border-b-2 px-2.5 text-sm font-medium whitespace-nowrap transition-colors",
                  active
                    ? "border-klyp-accent text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {c.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
