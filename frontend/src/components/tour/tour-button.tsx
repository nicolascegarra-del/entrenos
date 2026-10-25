"use client";

import { CircleHelp } from "lucide-react";
import { usePathname } from "next/navigation";

import { useTour } from "@/components/tour/tour-provider";
import { Button } from "@/components/ui/button";
import { useModules } from "@/hooks/use-api";
import { tourForPath } from "@/lib/tours";
import { cn } from "@/lib/utils";

/**
 * «?» que explica la pantalla actual (solo si tiene tour). Va en la barra superior del móvil y en la
 * cabecera de la pantalla en el PC.
 */
export function TourButton({ className }: { className?: string }) {
  const pathname = usePathname();
  const { start } = useTour();
  const { data: modules } = useModules();
  const tour = tourForPath(pathname, modules);
  if (!tour) return null;
  return (
    <Button
      variant="ghost"
      size="icon"
      data-tour="tour-help"
      className={cn("size-11 text-muted-foreground md:size-9", className)}
      aria-label={`Explícame esta pantalla (${tour.title})`}
      title="Explícame esta pantalla"
      onClick={() => start(tour.key)}
    >
      <CircleHelp aria-hidden />
    </Button>
  );
}
