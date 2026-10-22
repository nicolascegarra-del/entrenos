"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";

import { FormNotice } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { ApiError, resendVerification } from "@/lib/api";

/** Aviso tras registrarse: revisar el email, con opción de reenviarlo. */
export function CheckEmail({
  email,
  message,
}: {
  email: string;
  message: string;
}) {
  const [sent, setSent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-3">
      <FormNotice>{message}</FormNotice>
      <p className="text-sm text-muted-foreground">
        El enlace caduca en 24 horas. Revisa también la carpeta de spam.
      </p>
      {sent ? (
        <p className="text-sm text-muted-foreground" role="status">
          {sent}
        </p>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="h-11 w-full"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setSent(await resendVerification(email));
            } catch (err) {
              setSent(
                err instanceof ApiError ? err.message : "No se pudo reenviar.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy && <Loader2 className="animate-spin" aria-hidden />}
          Reenviar el email
        </Button>
      )}
    </div>
  );
}
