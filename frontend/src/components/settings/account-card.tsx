"use client";

import {
  Compass,
  Download,
  KeyRound,
  Loader2,
  LogOut,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  NewPasswordFields,
  passwordReady,
} from "@/components/auth/new-password-fields";
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
import { useMe } from "@/hooks/use-api";
import { describeLimits } from "@/lib/limits";
import {
  ApiError,
  apiFetch,
  authFetch,
  changePassword,
  parseError,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

function ChangePassword({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="space-y-3 rounded-lg border p-3"
      noValidate
      onSubmit={async (e) => {
        e.preventDefault();
        if (!current || !passwordReady(password, repeat)) return;
        setSaving(true);
        try {
          await changePassword(current, password);
          toast.success(
            "Contraseña cambiada. Se han cerrado tus otras sesiones.",
          );
          onDone();
        } catch (err) {
          toast.error(errorText(err));
        } finally {
          setSaving(false);
        }
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="current-password">Contraseña actual</Label>
        <Input
          id="current-password"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="h-11 md:h-9"
        />
      </div>
      <NewPasswordFields
        label="Contraseña nueva"
        password={password}
        repeat={repeat}
        onPassword={setPassword}
        onRepeat={setRepeat}
      />
      <Button
        type="submit"
        className="min-h-11 md:min-h-9"
        disabled={saving || !current || !passwordReady(password, repeat)}
      >
        {saving && <Loader2 className="animate-spin" />}
        Guardar contraseña
      </Button>
    </form>
  );
}

function DeleteAccount({ onCancel }: { onCancel: () => void }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-3 rounded-lg border border-destructive/40 p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (
          !window.confirm(
            "¿Seguro? Se borrarán tu cuenta y TODOS tus datos (actividades, plan, objetivos, conversaciones). No se puede deshacer.",
          )
        )
          return;
        setBusy(true);
        try {
          await apiFetch<void>("/api/v1/auth/me", {
            method: "DELETE",
            body: JSON.stringify({ password }),
          });
          useAuthStore.getState().setAccessToken(null);
          router.replace("/login");
        } catch (err) {
          toast.error(errorText(err));
          setBusy(false);
        }
      }}
    >
      <p className="text-sm">
        Se borrarán tu cuenta y todos tus datos. Descárgalos antes si quieres
        conservarlos.
      </p>
      <div className="space-y-2">
        <Label htmlFor="delete-password">Tu contraseña para confirmar</Label>
        <Input
          id="delete-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 md:h-9"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          variant="destructive"
          className="min-h-11 md:min-h-9"
          disabled={busy || !password}
        >
          {busy && <Loader2 className="animate-spin" />}
          Borrar mi cuenta
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="min-h-11 md:min-h-9"
          onClick={onCancel}
        >
          Cancelar
        </Button>
      </div>
    </form>
  );
}

/** Mi cuenta: contraseña, sesiones, exportar datos y darse de baja. */
export function AccountCard() {
  const router = useRouter();
  const { data: me } = useMe();
  const [open, setOpen] = useState<"password" | "delete" | null>(null);
  const [busy, setBusy] = useState<"logout" | "export" | null>(null);

  const logoutAll = async () => {
    if (
      !window.confirm(
        "Se cerrará la sesión en todos tus dispositivos, también en este.",
      )
    )
      return;
    setBusy("logout");
    try {
      await apiFetch<void>("/api/v1/auth/logout-all", { method: "POST" });
      useAuthStore.getState().setAccessToken(null);
      router.replace("/login");
    } catch (err) {
      toast.error(errorText(err));
      setBusy(null);
    }
  };

  const exportData = async () => {
    setBusy("export");
    try {
      const res = await authFetch("/api/v1/auth/me/export");
      if (!res.ok) throw await parseError(res);
      const name =
        res.headers
          .get("Content-Disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ?? "entrenos-mis-datos.json";
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <KeyRound className="size-5 text-klyp-accent" aria-hidden />
          Cuenta
        </CardTitle>
        <CardDescription>{me?.email}</CardDescription>
        {me && (
          <p className="text-sm">
            {me.tier === "basic" ? (
              <>
                <strong>Cuenta Básica</strong>:{" "}
                {describeLimits(me.limits).join(" · ")}. Un administrador puede
                ampliarla.
              </>
            ) : (
              <>
                <strong>Cuenta Completa</strong>, sin límites.
              </>
            )}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            aria-expanded={open === "password"}
            onClick={() => setOpen(open === "password" ? null : "password")}
          >
            <KeyRound aria-hidden /> Cambiar contraseña
          </Button>
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            onClick={logoutAll}
            disabled={busy === "logout"}
          >
            <LogOut aria-hidden /> Cerrar sesión en todos los dispositivos
          </Button>
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            onClick={exportData}
            disabled={busy === "export"}
          >
            {busy === "export" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Download aria-hidden />
            )}
            Descargar mis datos
          </Button>
          <Button asChild variant="outline" className="min-h-11 md:min-h-9">
            <Link href="/bienvenida">
              <Compass aria-hidden /> Repetir la configuración guiada
            </Link>
          </Button>
          <Button
            variant="ghost"
            className="min-h-11 text-destructive md:min-h-9"
            aria-expanded={open === "delete"}
            onClick={() => setOpen(open === "delete" ? null : "delete")}
          >
            <Trash2 aria-hidden /> Borrar mi cuenta
          </Button>
        </div>
        {open === "password" && <ChangePassword onDone={() => setOpen(null)} />}
        {open === "delete" && <DeleteAccount onCancel={() => setOpen(null)} />}
        {me?.is_admin && (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <ShieldCheck className="size-4 text-klyp-accent" aria-hidden />
            Eres administrador: gestiona usuarios e invitaciones en{" "}
            <Link
              href="/admin"
              className="font-medium text-klyp-accent hover:underline"
            >
              Admin
            </Link>
            .
          </p>
        )}
      </CardContent>
    </Card>
  );
}
