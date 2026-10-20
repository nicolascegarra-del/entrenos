"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";

/**
 * Enlace de un solo uso recién generado (invitación o contraseña): solo se puede
 * ver ahora, así que se muestra con botón de copiar y su caducidad.
 */
export function CopyLink({
  link,
  expiresAt,
  emailed,
  onClose,
}: {
  link: string;
  expiresAt: string;
  emailed: boolean;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-2 rounded-lg border border-klyp-accent/40 bg-klyp-pale/60 p-3 text-sm dark:bg-klyp-navy-light/40">
      <p className="font-medium">
        {emailed
          ? "Enviado por email. También puedes copiarlo:"
          : "Cópialo y envíaselo (WhatsApp, email…):"}
      </p>
      <div className="flex gap-2">
        <input
          readOnly
          value={link}
          aria-label="Enlace"
          className="h-11 min-w-0 flex-1 rounded-md border bg-background px-2 font-mono text-xs md:h-9"
          onFocus={(e) => e.target.select()}
        />
        <Button
          type="button"
          className="min-h-11 shrink-0 md:min-h-9"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(link);
              setCopied(true);
              toast.success("Enlace copiado.");
            } catch {
              toast.error("No se pudo copiar; selecciónalo y cópialo a mano.");
            }
          }}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          Copiar
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Un solo uso · caduca el {formatDateTime(expiresAt)} · no se podrá volver
        a ver.{" "}
        <button
          type="button"
          className="font-medium text-klyp-accent underline"
          onClick={onClose}
        >
          Cerrar
        </button>
      </p>
    </div>
  );
}
