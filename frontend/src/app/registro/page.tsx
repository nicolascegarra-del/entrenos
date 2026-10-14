"use client";

import { Activity, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch, registerWithInvitation } from "@/lib/api";

const MIN_PASSWORD = 10;

function RegisterForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setInvalid("Falta el enlace de invitación.");
      return;
    }
    apiFetch<{ email: string }>(
      `/api/v1/invitations/check?token=${encodeURIComponent(token)}`,
      {},
      false,
    )
      .then((res) => setEmail(res.email))
      .catch((err) =>
        setInvalid(
          err instanceof ApiError ? err.message : "La invitación no es válida.",
        ),
      );
  }, [token]);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = repeat.length > 0 && repeat !== password;

  return (
    <Card className="w-full max-w-sm shadow-md">
      <CardHeader className="items-center text-center">
        <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-lg bg-klyp-pale text-klyp-navy">
          <Activity className="size-6" aria-hidden />
        </div>
        <CardTitle className="font-heading text-2xl font-bold">
          Crea tu cuenta
        </CardTitle>
        <CardDescription>
          {email ? `Te han invitado como ${email}` : "APP ENTRENOS"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {invalid ? (
          <p
            role="alert"
            className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
          >
            {invalid} Pide un enlace nuevo a quien te invitó.
          </p>
        ) : !email ? (
          <Loader2
            className="mx-auto size-6 animate-spin text-klyp-accent"
            aria-label="Comprobando invitación"
          />
        ) : (
          <form
            className="space-y-4"
            noValidate
            onSubmit={async (e) => {
              e.preventDefault();
              if (password.length < MIN_PASSWORD || password !== repeat) return;
              setSubmitting(true);
              setError(null);
              try {
                await registerWithInvitation(token, password);
                router.replace("/ajustes");
              } catch (err) {
                setError(
                  err instanceof ApiError
                    ? err.message
                    : "No se pudo crear la cuenta.",
                );
                setSubmitting(false);
              }
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                aria-invalid={tooShort}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p
                className={
                  tooShort
                    ? "text-sm text-destructive"
                    : "text-xs text-muted-foreground"
                }
              >
                Mínimo {MIN_PASSWORD} caracteres.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="repeat">Repite la contraseña</Label>
              <Input
                id="repeat"
                type="password"
                autoComplete="new-password"
                value={repeat}
                aria-invalid={mismatch}
                onChange={(e) => setRepeat(e.target.value)}
              />
              {mismatch && (
                <p className="text-sm text-destructive">No coincide.</p>
              )}
            </div>
            {error && (
              <p
                role="alert"
                className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
              >
                {error}
              </p>
            )}
            <Button
              type="submit"
              className="h-11 w-full"
              disabled={
                submitting ||
                password.length < MIN_PASSWORD ||
                password !== repeat
              }
            >
              {submitting && <Loader2 className="animate-spin" aria-hidden />}{" "}
              Crear cuenta
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default function RegistroPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-klyp-navy p-4">
      <Suspense>
        <RegisterForm />
      </Suspense>
    </main>
  );
}
