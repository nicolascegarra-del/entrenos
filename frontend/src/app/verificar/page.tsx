"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { AuthShell, FormError, FormNotice } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { ApiError, verifyEmail } from "@/lib/api";

function Verify() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"working" | "pending" | "error">(
    "working",
  );
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    // El enlace es de un solo uso: evita gastarlo dos veces (StrictMode monta dos veces en desarrollo).
    if (started.current) return;
    started.current = true;
    if (!token) {
      setError("Falta el enlace de confirmación.");
      setState("error");
      return;
    }
    verifyEmail(token)
      .then((status) => {
        if (status === "active") router.replace("/ajustes");
        else setState("pending");
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Enlace no válido.");
        setState("error");
      });
  }, [token, router]);

  if (state === "pending")
    return (
      <FormNotice>
        Email confirmado. Un administrador revisará tu solicitud y te avisaremos
        por email cuando puedas entrar.
      </FormNotice>
    );
  if (state === "error")
    return (
      <>
        <FormError>{error}</FormError>
        <p className="mt-4 text-sm text-muted-foreground">
          Si el enlace ha caducado, intenta iniciar sesión: podrás pedir uno
          nuevo.
        </p>
        <Button asChild className="mt-4 h-11 w-full">
          <Link href="/login">Ir a iniciar sesión</Link>
        </Button>
      </>
    );
  return (
    <Loader2
      className="mx-auto size-6 animate-spin text-klyp-accent"
      aria-label="Confirmando tu email"
    />
  );
}

/** Confirmación del email del autoregistro (enlace de un solo uso). */
export default function VerificarPage() {
  return (
    <AuthShell title="Confirmar email">
      <Suspense>
        <Verify />
      </Suspense>
    </AuthShell>
  );
}
