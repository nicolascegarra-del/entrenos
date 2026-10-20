"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AuthShell, FormError, FormNotice } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthOptions } from "@/hooks/use-api";
import { ApiError, apiFetch } from "@/lib/api";

/** Pedir un enlace para restablecer la contraseña por email. */
export default function RecuperarPage() {
  const { data: options, isPending } = useAuthOptions();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  return (
    <AuthShell
      title="Recuperar contraseña"
      description="Te enviamos un enlace para elegir una nueva"
    >
      {isPending ? (
        <Skeleton className="h-24" />
      ) : !options?.email_enabled ? (
        <FormNotice>
          Esta instalación no envía emails. Pide a un administrador un enlace
          para restablecer tu contraseña: lo genera desde Admin → Usuarios.
        </FormNotice>
      ) : sent ? (
        <FormNotice>{sent} Revisa también la carpeta de spam.</FormNotice>
      ) : (
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setSubmitting(true);
            setError(null);
            try {
              const res = await apiFetch<{ message: string }>(
                "/api/v1/auth/forgot",
                { method: "POST", body: JSON.stringify({ email }) },
                false,
              );
              setSent(res.message);
            } catch (err) {
              setError(
                err instanceof ApiError ? err.message : "No se pudo enviar.",
              );
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="email">Email de tu cuenta</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 md:h-9"
            />
          </div>
          {error && <FormError>{error}</FormError>}
          <Button type="submit" className="h-11 w-full" disabled={submitting}>
            {submitting && <Loader2 className="animate-spin" aria-hidden />}
            Enviar enlace
          </Button>
        </form>
      )}
      <p className="mt-4 text-center text-sm">
        <Link
          href="/login"
          className="font-medium text-klyp-accent hover:underline"
        >
          Volver a iniciar sesión
        </Link>
      </p>
    </AuthShell>
  );
}
