"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Activity, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

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
import { ApiError, login } from "@/lib/api";

const schema = z.object({
  email: z.email("Introduce un email válido."),
  password: z.string().min(1, "Introduce tu contraseña."),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit({ email, password }: FormValues) {
    setServerError(null);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "No se pudo iniciar sesión.",
      );
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-klyp-navy p-4">
      <Card className="w-full max-w-sm shadow-md">
        <CardHeader className="items-center text-center">
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-lg bg-klyp-pale text-klyp-navy">
            <Activity className="size-6" aria-hidden />
          </div>
          <CardTitle className="font-heading text-2xl font-bold">
            APP ENTRENOS
          </CardTitle>
          <CardDescription>
            Inicia sesión para ver tus entrenamientos
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
          >
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-invalid={!!errors.email}
                {...register("email")}
              />
              {errors.email && (
                <p className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                {...register("password")}
              />
              {errors.password && (
                <p className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>
            {serverError && (
              <p
                role="alert"
                className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
              >
                {serverError}
              </p>
            )}
            <Button
              type="submit"
              className="h-11 w-full"
              disabled={isSubmitting}
            >
              {isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
              Entrar
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
