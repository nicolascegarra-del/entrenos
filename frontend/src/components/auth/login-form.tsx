"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CheckEmail } from "@/components/auth/check-email";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AuthOptions } from "@/types/api";
import { ApiError, login } from "@/lib/api";

const schema = z.object({
  email: z.email("Introduce un email válido."),
  password: z.string().min(1, "Introduce tu contraseña."),
});
type FormValues = z.infer<typeof schema>;

/** Formulario de inicio de sesión (en la landing de /login). */
export function LoginForm({ options }: { options?: AuthOptions }) {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const [unverified, setUnverified] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit({ email, password }: FormValues) {
    setServerError(null);
    setUnverified(null);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_NOT_VERIFIED")
        setUnverified(email);
      setServerError(
        err instanceof ApiError ? err.message : "No se pudo iniciar sesión.",
      );
    }
  }

  return (
    <>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            className="h-11"
            aria-invalid={!!errors.email}
            {...register("email")}
          />
          {errors.email && (
            <p className="text-sm text-destructive">{errors.email.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Contraseña</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            className="h-11"
            aria-invalid={!!errors.password}
            {...register("password")}
          />
          {errors.password && (
            <p className="text-sm text-destructive">
              {errors.password.message}
            </p>
          )}
        </div>
        {unverified ? (
          <CheckEmail email={unverified} message={serverError ?? ""} />
        ) : (
          serverError && (
            <p
              role="alert"
              className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
            >
              {serverError}
            </p>
          )
        )}
        <Button type="submit" className="h-11 w-full" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
          Entrar
        </Button>
      </form>
      <div className="mt-4 space-y-2 text-center text-sm">
        <p>
          <Link
            href="/recuperar"
            className="inline-flex min-h-11 items-center font-medium text-klyp-accent hover:underline"
          >
            ¿Has olvidado tu contraseña?
          </Link>
        </p>
        {options?.signup_available && (
          <p>
            ¿No tienes cuenta?{" "}
            <Link
              href="/registro"
              className="font-medium text-klyp-accent hover:underline"
            >
              {options.registration === "approval" ? "Solicita una" : "Créala"}
            </Link>
          </p>
        )}
      </div>
    </>
  );
}
