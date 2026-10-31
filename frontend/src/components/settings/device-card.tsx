"use client";

import {
  CircleAlert,
  ExternalLink,
  Loader2,
  QrCode,
  RefreshCw,
  Smartphone,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useConnectDevice,
  useBrandAccounts,
  useDisconnectDevice,
  useSamsungFinish,
  useSamsungStart,
  useSyncDevice,
  useXiaomiQr,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { DeviceConnection, DeviceProvider, XiaomiQr } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const BRAND: Record<DeviceProvider, { name: string; note: string }> = {
  suunto: {
    name: "Suunto",
    note: "Usa tu email y contraseña de la app Suunto. Suunto te enviará un email avisando del inicio de sesión.",
  },
  zepp: {
    name: "Zepp",
    note: "Usa tu email y contraseña de la app Zepp (relojes Amazfit y Mi Band antiguas).",
  },
  xiaomi: {
    name: "Xiaomi",
    note: "Xiaomi no permite entrar con contraseña desde otras apps: se conecta con un QR que apruebas en el móvil. En beta: de momento se trae el resumen de cada entreno (sin el detalle segundo a segundo).",
  },
  samsung: {
    name: "Samsung",
    note: "Inicias sesión en la propia web de Samsung (tu contraseña no pasa por aquí). En beta: se trae el resumen de cada entreno. Si tienes activado el cifrado de datos en Samsung Health, no se podrán leer.",
  },
};

const REGIONS = [
  { key: "de", label: "Europa" },
  { key: "us", label: "América" },
  { key: "sg", label: "Asia y resto" },
  { key: "ru", label: "Rusia" },
  { key: "cn", label: "China" },
];

/** Estado de una conexión: sincronizar, desconectar y el error si lo hay. */
function Connected({ conn }: { conn: DeviceConnection }) {
  const sync = useSyncDevice(conn.provider);
  const disconnect = useDisconnectDevice(conn.provider);
  return (
    <div className="space-y-2">
      <p className="text-sm">
        Conectado como <strong>{conn.account}</strong>
        {conn.last_sync_at &&
          ` · última sincronización ${formatDateTime(conn.last_sync_at)}`}
      </p>
      {conn.status !== "ok" && (
        <p className="flex items-start gap-1.5 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {conn.last_error ||
            "Hay un problema con la conexión: vuelve a conectar la cuenta."}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={sync.isPending || conn.status === "expired"}
          onClick={() =>
            sync.mutate(undefined, {
              onSuccess: () =>
                toast.success(
                  "Sincronizando: tus entrenos aparecerán en unos minutos.",
                ),
              onError: (err) => toast.error(errorText(err)),
            })
          }
        >
          <RefreshCw aria-hidden /> Sincronizar ahora
        </Button>
        <Button
          variant="ghost"
          className="min-h-11 text-destructive md:min-h-9"
          disabled={disconnect.isPending}
          onClick={() =>
            disconnect.mutate(undefined, {
              onSuccess: () =>
                toast.success(
                  "Desconectado. Tus entrenos ya traídos se quedan.",
                ),
              onError: (err) => toast.error(errorText(err)),
            })
          }
        >
          <Trash2 aria-hidden /> Desconectar
        </Button>
      </div>
    </div>
  );
}

function PasswordForm({ provider }: { provider: "suunto" | "zepp" }) {
  const connect = useConnectDevice(provider);
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  return (
    <form
      className="grid gap-2 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        connect.mutate(
          { account: account.trim(), password },
          {
            onSuccess: () => {
              setPassword("");
              toast.success(
                `${BRAND[provider].name} conectado. Importando tus entrenos…`,
              );
            },
            onError: (err) => toast.error(errorText(err)),
          },
        );
      }}
    >
      <div className="space-y-1">
        <Label htmlFor={`${provider}-account`}>Email</Label>
        <Input
          id={`${provider}-account`}
          type="email"
          autoComplete="username"
          required
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${provider}-password`}>Contraseña</Label>
        <Input
          id={`${provider}-password`}
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <div className="md:col-span-2">
        <Button
          type="submit"
          className="min-h-11 md:min-h-9"
          disabled={connect.isPending}
        >
          {connect.isPending && (
            <Loader2 className="animate-spin" aria-hidden />
          )}
          Conectar
        </Button>
      </div>
    </form>
  );
}

function XiaomiForm({ pending }: { pending: boolean }) {
  const start = useXiaomiQr();
  const [region, setRegion] = useState("de");
  const [qr, setQr] = useState<XiaomiQr | null>(null);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="xiaomi-region">Región de tu cuenta</Label>
          <select
            id="xiaomi-region"
            className="flex h-11 rounded-md border bg-background px-3 text-sm md:h-9"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            {REGIONS.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <Button
          className="min-h-11 md:min-h-9"
          disabled={start.isPending}
          onClick={() =>
            start.mutate(region, {
              onSuccess: setQr,
              onError: (err) => toast.error(errorText(err)),
            })
          }
        >
          {start.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <QrCode aria-hidden />
          )}
          {qr ? "Generar otro QR" : "Mostrar el QR"}
        </Button>
      </div>
      {qr && pending && (
        <div className="flex flex-col items-start gap-2 rounded-lg border p-3 sm:flex-row sm:items-center">
          {/* eslint-disable-next-line @next/next/no-img-element -- imagen externa de Xiaomi, de un solo uso */}
          <img
            src={qr.qr}
            alt="QR para aprobar el inicio de sesión en Xiaomi"
            className="size-40 rounded bg-white p-1"
          />
          {/* La cámara del móvil abre el enlace en el navegador, sin sesión de Xiaomi, y Xiaomi lo
              rechaza (código 70016): hay que escanearlo desde una app de Xiaomi con la sesión iniciada. */}
          <div className="space-y-2 text-sm">
            <p className="flex items-start gap-1.5 font-medium">
              <Smartphone className="mt-0.5 size-4 shrink-0" aria-hidden />
              Escanéalo desde la app <strong>Xiaomi Home</strong> (botón + →
              Escanear), con tu cuenta ya iniciada, y aprueba el inicio de
              sesión.
            </p>
            <p className="text-muted-foreground">
              No uses la cámara del móvil: abre el enlace en el navegador y
              Xiaomi lo rechaza. El QR dura unos 2 minutos. Esperando…
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Samsung: se abre su web para iniciar sesión y, al terminar, el navegador no sabe abrir el enlace
 * «ms-app://…» al que vuelve Samsung: solo aparece en la consola (F12). La persona lo copia y lo pega aquí.
 */
function SamsungForm({ pending }: { pending: boolean }) {
  const start = useSamsungStart();
  const finish = useSamsungFinish();
  const [redirect, setRedirect] = useState("");
  return (
    <div className="space-y-3">
      <ol className="list-decimal space-y-1 pl-5 text-sm">
        <li>
          Pulsa «Iniciar sesión en Samsung» y entra con tu cuenta en la pestaña
          que se abre.
        </li>
        <li>
          Al terminar, la página se queda parada. Pulsa <strong>F12</strong> →
          pestaña <strong>Consola</strong> y copia el enlace que empieza por{" "}
          <code>ms-app://</code> (sale en un error en rojo).
        </li>
        <li>Pégalo abajo y pulsa «Conectar». Tienes 15 minutos.</li>
      </ol>
      <Button
        className="min-h-11 md:min-h-9"
        disabled={start.isPending}
        onClick={() =>
          start.mutate(undefined, {
            onSuccess: ({ login_url }) =>
              window.open(login_url, "_blank", "noopener"),
            onError: (err) => toast.error(errorText(err)),
          })
        }
      >
        {start.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <ExternalLink aria-hidden />
        )}
        Iniciar sesión en Samsung
      </Button>
      {pending && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            finish.mutate(redirect.trim(), {
              onSuccess: () => {
                setRedirect("");
                toast.success("Samsung conectado. Importando tus entrenos…");
              },
              onError: (err) => toast.error(errorText(err)),
            });
          }}
        >
          <Label htmlFor="samsung-redirect">Enlace «ms-app://…»</Label>
          <Input
            id="samsung-redirect"
            required
            placeholder="ms-app://s-1-15-2-…"
            value={redirect}
            onChange={(e) => setRedirect(e.target.value)}
          />
          <Button
            type="submit"
            className="min-h-11 md:min-h-9"
            disabled={finish.isPending || !redirect.trim()}
          >
            {finish.isPending && (
              <Loader2 className="animate-spin" aria-hidden />
            )}
            Conectar
          </Button>
        </form>
      )}
    </div>
  );
}

/**
 * Conexión con la cuenta de Suunto, Amazfit (Zepp) o Xiaomi. No oficial: si la marca la rompe, se ve el
 * error aquí y el administrador puede apagarla en Admin → Módulos.
 */
export function DeviceCard({ provider }: { provider: DeviceProvider }) {
  const devices = useBrandAccounts();
  const conn = devices.data?.connections.find((c) => c.provider === provider);
  // Un QR de Xiaomi que caducó deja la conexión sin cuenta: se vuelve a ofrecer el QR con el error.
  const live = conn && conn.status !== "pending" && !!conn.account;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{BRAND[provider].note}</p>
      {live && <Connected conn={conn} />}
      {conn && !live && conn.last_error && (
        <p className="flex items-start gap-1.5 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {conn.last_error}
        </p>
      )}
      {(!live || conn.status === "expired") &&
        (provider === "xiaomi" ? (
          <XiaomiForm pending={conn?.status === "pending"} />
        ) : provider === "samsung" ? (
          <SamsungForm pending={conn?.status === "pending"} />
        ) : (
          <PasswordForm provider={provider} />
        ))}
      <p className="text-xs text-muted-foreground">
        Conexión no oficial: puede dejar de funcionar si la marca cambia su app.
        La contraseña no se guarda, solo la sesión (cifrada).
      </p>
    </div>
  );
}
