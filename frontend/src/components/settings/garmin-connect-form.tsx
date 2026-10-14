"use client";

import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useConnectState,
  useSendMfaCode,
  useStartGarminConnect,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";

const STEP_TEXT = {
  pending: "Conectando con Garmin…",
  verifying: "Verificando el código…",
} as const;

/**
 * Conecta Garmin desde la web: email y contraseña → (código de verificación si Garmin lo pide).
 * La contraseña solo viaja cifrada al servidor para iniciar sesión; se guardan únicamente los tokens.
 */
export function GarminConnectForm({
  reconnect = false,
}: {
  reconnect?: boolean;
}) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [connectId, setConnectId] = useState<string | null>(null);
  const start = useStartGarminConnect();
  const { data: state } = useConnectState(connectId);
  const sendCode = useSendMfaCode(connectId);

  useEffect(() => {
    if (state?.status === "connected") {
      toast.success("Garmin conectado");
      setConnectId(null);
      setPassword("");
      for (const key of ["garmin-status", "profile"])
        queryClient.invalidateQueries({ queryKey: [key] });
    }
    if (state?.status === "error") setPassword("");
  }, [state?.status, queryClient]);

  const busy =
    start.isPending ||
    state?.status === "pending" ||
    state?.status === "verifying";

  if (state?.status === "needs_mfa") {
    return (
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          sendCode.mutate(code.trim(), {
            onError: (err) =>
              toast.error(
                err instanceof ApiError
                  ? err.message
                  : "No se pudo enviar el código.",
              ),
          });
        }}
      >
        <p className="flex items-start gap-2 text-sm">
          <ShieldCheck
            className="mt-0.5 size-4 shrink-0 text-klyp-accent"
            aria-hidden
          />
          Garmin te ha enviado un código de verificación (email o app).
          Escríbelo aquí; tienes 5 minutos.
        </p>
        <div className="space-y-1">
          <Label htmlFor="mfa-code">Código</Label>
          <Input
            id="mfa-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{4,8}"
            maxLength={8}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="h-11 max-w-40 tracking-widest md:h-9"
          />
        </div>
        <Button
          type="submit"
          className="min-h-11"
          disabled={!/^\d{4,8}$/.test(code.trim()) || sendCode.isPending}
        >
          {sendCode.isPending && (
            <Loader2 className="animate-spin" aria-hidden />
          )}{" "}
          Verificar
        </Button>
      </form>
    );
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        start.mutate(
          { email: email.trim(), password },
          {
            onSuccess: (res) => setConnectId(res.connect_id),
            onError: (err) =>
              toast.error(
                err instanceof ApiError
                  ? err.message
                  : "No se pudo iniciar la conexión.",
              ),
          },
        );
      }}
    >
      {reconnect && (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200">
          La sesión de Garmin ha caducado. Vuelve a conectar para seguir
          sincronizando.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="garmin-email">Email de Garmin Connect</Label>
          <Input
            id="garmin-email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 md:h-9"
            disabled={busy}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="garmin-password">Contraseña de Garmin</Label>
          <Input
            id="garmin-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 md:h-9"
            disabled={busy}
          />
        </div>
      </div>
      {state?.status === "error" && state.error && (
        <p
          role="alert"
          className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
        >
          {state.error}
        </p>
      )}
      <Button
        type="submit"
        className="min-h-11"
        disabled={busy || !email.trim() || !password}
      >
        {busy ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <KeyRound aria-hidden />
        )}
        {busy && state?.status
          ? (STEP_TEXT[state.status as keyof typeof STEP_TEXT] ?? "Conectando…")
          : reconnect
            ? "Reconectar"
            : "Conectar Garmin"}
      </Button>
      <p className="text-xs text-muted-foreground">
        La contraseña solo se usa para iniciar sesión y no se guarda: la app
        conserva únicamente los tokens de sesión, cifrados. Puedes desconectar
        cuando quieras.
      </p>
    </form>
  );
}
