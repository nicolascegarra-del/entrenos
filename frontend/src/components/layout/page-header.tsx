import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * Cabecera común de pantalla: volver (en subpáginas), título, subtítulo y acciones a la derecha.
 * Sustituye a las cabeceras y enlaces «← Sección» hechos a mano en cada página.
 */
export function PageHeader({
  title,
  subtitle,
  back,
  actions,
  hideTitleOnMobile = false,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Página padre: muestra «← label» encima del título. */
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  /** En portadas de sección el título ya va en la barra superior del móvil: no se repite. */
  hideTitleOnMobile?: boolean;
}) {
  return (
    <header className="mb-4 space-y-1">
      {back && (
        <Link
          href={back.href}
          className="-ml-1 inline-flex min-h-11 items-center gap-1 rounded-md px-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden /> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h1
            className={cn(
              "font-heading text-2xl font-bold break-words md:text-3xl",
              hideTitleOnMobile && "max-lg:sr-only",
            )}
          >
            {title}
          </h1>
          {subtitle && (
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </header>
  );
}
