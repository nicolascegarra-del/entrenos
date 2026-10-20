"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthShell, FormError, FormNotice } from "@/components/auth/auth-shell";
import {
  NewPasswordFields,
  passwordReady,
} from "@/components/auth/new-password-fields";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setInvalid("Falta el enlace.");
      return;
    }
    apiFetch<{ email: string }>(
      `/api/v1/auth/reset/check?token=${encodeURIComponent(token)}`,
      {},
      false,
    )
      .then((res) => setEmail(res.email))
      .catch((err) =>
        setInvalid(err instanceof ApiError ? err.message : "Enlace no válido."),
      );
  }, [token]);

  if (invalid)
    return (
      <>
        <FormError>{invalid}</FormError>
        <p className="mt-4 text-center text-sm">
          <Link
            href="/recuperar"
            className="font-medium text-klyp-accent hover:underline"
          >
            Pedir un enlace nuevo
          </Link>
        </p>
      </>
    );
  if (done)
    return (
      <>
        <FormNotice>
          Contraseña cambiada. Hemos cerrado la sesión en todos tus
          dispositivos.
        </FormNotice>
        <Button asChild className="mt-4 h-11 w-full">
          <Link href="/login">Iniciar sesión</Link>
        </Button>
      </>
    );
  if (!email)
    return (
      <Loader2
        className="mx-auto size-6 animate-spin text-klyp-accent"
        aria-label="Comprobando enlace"
      />
    );
  return (
    <form
      className="space-y-4"
      noValidate
      onSubmit={async (e) => {
        e.preventDefault();
        if (!passwordReady(password, repeat)) return;
        setSubmitting(true);
        setError(null);
        try {
          await apiFetch<void>(
            "/api/v1/auth/reset",
            { method: "POST", body: JSON.stringify({ token, password }) },
            false,
          );
          setDone(true);
        } catch (err) {
          setError(
            err instanceof ApiError ? err.message : "No se pudo cambiar.",
          );
        } finally {
          setSubmitting(false);
        }
      }}
    >
      <p className="text-sm text-muted-foreground">Cuenta: {email}</p>
      <NewPasswordFields
        label="Contraseña nueva"
        password={password}
        repeat={repeat}
        onPassword={setPassword}
        onRepeat={setRepeat}
      />
      {error && <FormError>{error}</FormError>}
      <Button
        type="submit"
        className="h-11 w-full"
        disabled={submitting || !passwordReady(password, repeat)}
      >
        {submitting && <Loader2 className="animate-spin" aria-hidden />}
        Guardar contraseña
      </Button>
    </form>
  );
}

/** Elegir contraseña nueva con el enlace de un solo uso (email o generado por un administrador). */
export default function RestablecerPage() {
  return (
    <AuthShell title="Contraseña nueva">
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
