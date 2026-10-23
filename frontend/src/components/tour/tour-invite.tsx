"use client";

import { Compass, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useTour } from "@/components/tour/tour-provider";
import { Button } from "@/components/ui/button";
import { seenTours } from "@/lib/tours";

const DISMISSED = "tour-invitacion-descartada";

/** Hoy, la primera vez: «¿Te enseño la app?». No vuelve si se descarta o se hace el tour general. */
export function TourInvite() {
  const { start, active } = useTour();
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(
        !localStorage.getItem(DISMISSED) &&
          !seenTours(localStorage).has("general"),
      );
    } catch {
      setShow(false);
    }
  }, []);

  const dismiss = () => {
    setShow(false);
    try {
      localStorage.setItem(DISMISSED, "1");
    } catch {
      // Sin almacenamiento: volverá a salir, sin más.
    }
  };

  if (!show || active) return null;
  return (
    <div className="flex items-start gap-3 rounded-lg border border-klyp-accent/50 bg-klyp-accent/5 p-3 text-sm">
      <Compass
        className="mt-0.5 size-5 shrink-0 text-klyp-accent"
        aria-hidden
      />
      <div className="min-w-0 flex-1 space-y-2">
        <p>
          <span className="block font-medium">
            ¿Te enseño la app en 2 minutos?
          </span>
          <span className="text-muted-foreground">
            Un paseo rápido por cada sección. Lo puedes repetir cuando quieras
            desde Más → Ayuda.
          </span>
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            className="min-h-11 md:min-h-8"
            onClick={() => {
              dismiss();
              start("general");
            }}
          >
            Empezar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="min-h-11 md:min-h-8"
            onClick={dismiss}
          >
            Ahora no
          </Button>
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="-mt-1 -mr-1 size-11 shrink-0 md:size-8"
        aria-label="Cerrar"
        onClick={dismiss}
      >
        <X aria-hidden />
      </Button>
    </div>
  );
}
