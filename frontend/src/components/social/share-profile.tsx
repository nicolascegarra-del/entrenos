"use client";

import { Copy, Share2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { profileUrl } from "@/lib/social";

/** Tu enlace de perfil (/u/@handle) para copiarlo o compartirlo con el menú del móvil. */
export function ShareProfile({ handle }: { handle: string }) {
  const [url, setUrl] = useState(`/u/${handle}`);
  const [canShare, setCanShare] = useState(false);
  useEffect(() => {
    setUrl(profileUrl(window.location.origin, handle));
    setCanShare(typeof navigator !== "undefined" && "share" in navigator);
  }, [handle]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Enlace copiado.");
    } catch {
      toast.error("No se pudo copiar: selecciónalo y cópialo a mano.");
    }
  };
  const share = async () => {
    try {
      await navigator.share({
        title: "Sígueme en KTrain",
        text: "Sígueme en KTrain para ver mis entrenos y retarme a un duelo.",
        url,
      });
    } catch {
      // Cancelado por la persona: no hay nada que avisar.
    }
  };

  return (
    <Card className="gap-0 py-0 shadow-sm" data-tour="share-profile">
      <CardContent className="space-y-2 p-3 md:p-4">
        <p className="text-sm font-medium">Tu enlace para que te sigan</p>
        <div className="flex flex-wrap items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded-md bg-muted px-3 py-2 font-mono text-sm">
            {url}
          </code>
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            onClick={copy}
          >
            <Copy aria-hidden /> Copiar
          </Button>
          {canShare && (
            <Button className="min-h-11 md:min-h-9" onClick={share}>
              <Share2 aria-hidden /> Compartir
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
