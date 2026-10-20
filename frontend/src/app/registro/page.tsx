"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthShell, FormError, FormNotice } from "@/components/auth/auth-shell";
import {
  NewPasswordFields,
  passwordReady,
} from "@/components/auth/new-password-fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthOptions } from "@/hooks/use-api";
import { ApiError, apiFetch, registerWithInvitation, signup } from "@/lib/api";

const errorText = (err: unknown) =>
  err instanceof ApiError ? err.message : "No se pudo crear la cuenta.";

function BackToLogin() {
  return (
    <p className="mt-4 text-center text-sm">
      ¿Ya tienes cuenta?{" "}
      <Link
        href="/login"
        className="font-medium text-klyp-accent hover:underline"
      >
        Inicia sesión
      </Link>
    </p>
  );
}

/** Alta con el enlace de invitación de un administrador. */
function InvitationForm({ token }: { token: string }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
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

  return (
    <AuthShell
      title="Crea tu cuenta"
      description={email ? `Te han invitado como ${email}` : "APP ENTRENOS"}
    >
      {invalid ? (
        <FormError>{invalid} Pide un enlace nuevo a quien te invitó.</FormError>
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
            if (!passwordReady(password, repeat)) return;
            setSubmitting(true);
            setError(null);
            try {
              await registerWithInvitation(token, password);
              router.replace("/ajustes");
            } catch (err) {
              setError(errorText(err));
              setSubmitting(false);
            }
          }}
        >
          <NewPasswordFields
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
            Crear cuenta
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

/** Alta sin invitación: registro abierto o con aprobación de un administrador. */
function SignupForm() {
  const router = useRouter();
  const { data: options, isPending } = useAuthOptions();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const approval = options?.registration === "approval";

  return (
    <AuthShell
      title="Crea tu cuenta"
      description={
        approval
          ? "Un administrador revisará tu solicitud"
          : "Para ver y analizar tus entrenamientos de Garmin"
      }
    >
      {isPending ? (
        <Skeleton className="h-40" />
      ) : options?.registration === "invite" ? (
        <FormNotice>
          El registro es solo con invitación. Pide a un administrador que te
          invite.
        </FormNotice>
      ) : pending ? (
        <FormNotice>
          Solicitud enviada. Podrás entrar cuando un administrador la apruebe
          {options?.email_enabled ? "; te avisaremos por email." : "."}
        </FormNotice>
      ) : (
        <form
          className="space-y-4"
          noValidate
          onSubmit={async (e) => {
            e.preventDefault();
            if (!email || !passwordReady(password, repeat)) return;
            setSubmitting(true);
            setError(null);
            try {
              const status = await signup(email, password);
              if (status === "active") router.replace("/ajustes");
              else setPending(true);
            } catch (err) {
              setError(errorText(err));
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
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
          <NewPasswordFields
            password={password}
            repeat={repeat}
            onPassword={setPassword}
            onRepeat={setRepeat}
          />
          {error && <FormError>{error}</FormError>}
          <Button
            type="submit"
            className="h-11 w-full"
            disabled={submitting || !email || !passwordReady(password, repeat)}
          >
            {submitting && <Loader2 className="animate-spin" aria-hidden />}
            {approval ? "Solicitar cuenta" : "Crear cuenta"}
          </Button>
        </form>
      )}
      <BackToLogin />
    </AuthShell>
  );
}

function RegisterSwitch() {
  const token = useSearchParams().get("token");
  return token ? <InvitationForm token={token} /> : <SignupForm />;
}

export default function RegistroPage() {
  return (
    <Suspense>
      <RegisterSwitch />
    </Suspense>
  );
}
