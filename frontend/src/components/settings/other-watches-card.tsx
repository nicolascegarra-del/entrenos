"use client";

import {
  Copy,
  FileUp,
  KeyRound,
  Link2,
  Loader2,
  RefreshCw,
  Smartphone,
  Trash2,
  Watch,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

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
import { Skeleton } from "@/components/ui/skeleton";
import {
  useConnectCoros,
  useDisconnectCoros,
  useImportFile,
  useIngestToken,
  useSources,
  useSyncCoros,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { fileToBase64, IMPORT_EXTENSIONS, importable } from "@/lib/files";
import { formatDateTime } from "@/lib/format";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Watch;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2 rounded-lg border p-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4 text-klyp-accent" aria-hidden /> {title}
      </h3>
      {children}
    </section>
  );
}

function ImportFiles() {
  const input = useRef<HTMLInputElement>(null);
  const upload = useImportFile();
  const [last, setLast] = useState<{ id: number; created: boolean } | null>(
    null,
  );
  const run = async (files: FileList) => {
    for (const file of Array.from(files)) {
      if (!importable(file.name)) {
        toast.error(`${file.name}: solo FIT, GPX o TCX.`);
        continue;
      }
      try {
        const r = await upload.mutateAsync({
          filename: file.name,
          content_b64: await fileToBase64(file),
        });
        setLast({ id: r.activity_id, created: r.created });
        toast.success(
          r.created
            ? `${file.name} importado.`
            : `${file.name} ya estaba (no se duplica).`,
        );
      } catch (err) {
        toast.error(`${file.name}: ${errorText(err)}`);
      }
    }
  };
  return (
    <Section icon={FileUp} title="Importar ficheros (cualquier reloj)">
      <p className="text-xs text-muted-foreground">
        FIT, GPX o TCX exportados desde Suunto, Polar, COROS, Wahoo, Amazfit
        (Zepp), Strava… Si el entreno ya estaba (por ejemplo, desde Garmin), no
        se duplica.
      </p>
      <input
        ref={input}
        type="file"
        multiple
        accept={IMPORT_EXTENSIONS.join(",")}
        className="sr-only"
        aria-label="Ficheros de actividad"
        onChange={(e) => {
          if (e.target.files?.length) run(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={upload.isPending}
          onClick={() => input.current?.click()}
        >
          {upload.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <FileUp aria-hidden />
          )}
          Elegir ficheros
        </Button>
        {last && (
          <Link
            href={`/actividades/${last.id}`}
            className="text-sm text-klyp-accent underline"
          >
            Ver la actividad
          </Link>
        )}
      </div>
    </Section>
  );
}

function Coros({
  data,
}: {
  data: NonNullable<ReturnType<typeof useSources>["data"]>;
}) {
  const connect = useConnectCoros();
  const sync = useSyncCoros();
  const disconnect = useDisconnectCoros();
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const c = data.coros;
  return (
    <Section icon={Watch} title="COROS">
      {c ? (
        <>
          <p className="text-sm">
            Conectado como <strong>{c.account}</strong>
            {c.last_sync_at &&
              ` · última sincronización ${formatDateTime(c.last_sync_at)}`}
          </p>
          {c.status !== "ok" && (
            <p className="text-sm text-destructive">
              {c.last_error ||
                "Hay un problema con la conexión: vuelve a conectar la cuenta."}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="min-h-11 md:min-h-9"
              disabled={sync.isPending || c.status === "expired"}
              onClick={() =>
                sync.mutate(undefined, {
                  onSuccess: () =>
                    toast.success(
                      "Sincronizando COROS: tus actividades aparecerán en unos minutos.",
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
                  onError: (err) => toast.error(errorText(err)),
                })
              }
            >
              <Trash2 aria-hidden /> Desconectar
            </Button>
          </div>
        </>
      ) : null}
      {(!c || c.status === "expired") && (
        <form
          className="grid gap-2 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            connect.mutate(
              { account: account.trim(), password },
              {
                onSuccess: () => {
                  setPassword("");
                  toast.success("COROS conectado. Importando tus actividades…");
                },
                onError: (err) => toast.error(errorText(err)),
              },
            );
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="coros-account">Email de COROS</Label>
            <Input
              id="coros-account"
              type="email"
              autoComplete="username"
              required
              className="h-11 md:h-9"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="coros-password">Contraseña de COROS</Label>
            <Input
              id="coros-password"
              type="password"
              autoComplete="current-password"
              required
              className="h-11 md:h-9"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <p className="text-xs text-muted-foreground md:col-span-2">
            Usa la web de COROS Training Hub (no es una API oficial y puede
            dejar de funcionar si COROS la cambia). La contraseña solo se usa
            para entrar y no se guarda.
          </p>
          <Button
            type="submit"
            className="min-h-11 md:col-span-2 md:min-h-9 md:w-fit"
            disabled={connect.isPending}
          >
            {connect.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Link2 aria-hidden />
            )}
            Conectar COROS
          </Button>
        </form>
      )}
    </Section>
  );
}

function HealthConnect({
  data,
}: {
  data: NonNullable<ReturnType<typeof useSources>["data"]>;
}) {
  const token = useIngestToken();
  const [plain, setPlain] = useState<string | null>(null);
  const hc = data.health_connect;
  const copy = (text: string) =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success("Copiado."))
      .catch(() => toast.error("No se pudo copiar."));
  return (
    <Section
      icon={Smartphone}
      title="Samsung, Xiaomi/Amazfit, Huawei y Wear OS (Health Connect)"
    >
      <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
        <li>
          En tu Android, sincroniza tu reloj con Health Connect desde su app
          (Samsung Health, Zepp, Mi Fitness, Huawei Health…).
        </li>
        <li>
          Instala la app libre{" "}
          <a
            href="https://github.com/mcnaveen/health-connect-webhook"
            target="_blank"
            rel="noreferrer noopener"
            className="text-klyp-accent underline"
          >
            Health Connect Webhook
          </a>{" "}
          y dale permiso para leer entrenamientos, pulso, sueño y pasos.
        </li>
        <li>
          Añade un webhook con esta URL y la cabecera{" "}
          <code className="rounded bg-muted px-1">X-Api-Key</code> con tu token.
        </li>
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1.5 text-xs">
          {data.ingest_url}
        </code>
        <Button
          variant="ghost"
          size="icon"
          className="size-11 md:size-8"
          aria-label="Copiar la URL"
          onClick={() => copy(data.ingest_url)}
        >
          <Copy aria-hidden />
        </Button>
      </div>
      {plain && (
        <div className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2 text-amber-950 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200">
          <p className="text-xs font-medium">
            Tu token (cópialo ahora: no se volverá a mostrar)
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate text-xs">{plain}</code>
            <Button
              variant="ghost"
              size="icon"
              className="size-11 md:size-8"
              aria-label="Copiar el token"
              onClick={() => copy(plain)}
            >
              <Copy aria-hidden />
            </Button>
          </div>
        </div>
      )}
      {hc && !plain && (
        <p className="text-xs text-muted-foreground">
          Token activo ••••{hc.hint}
          {hc.last_used_at
            ? ` · último envío ${formatDateTime(hc.last_used_at)}`
            : " · aún no ha recibido datos"}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          className="min-h-11 md:min-h-9"
          disabled={token.isPending}
          onClick={() => {
            if (
              hc &&
              !window.confirm(
                "¿Crear un token nuevo? El anterior dejará de funcionar.",
              )
            )
              return;
            token.mutate(false, {
              onSuccess: (r) => r && setPlain(r.token),
              onError: (err) => toast.error(errorText(err)),
            });
          }}
        >
          <KeyRound aria-hidden /> {hc ? "Renovar token" : "Crear token"}
        </Button>
        {hc && (
          <Button
            variant="ghost"
            className="min-h-11 text-destructive md:min-h-9"
            disabled={token.isPending}
            onClick={() =>
              token.mutate(true, {
                onSuccess: () => setPlain(null),
                onError: (err) => toast.error(errorText(err)),
              })
            }
          >
            <Trash2 aria-hidden /> Revocar
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Llegan los entrenos (con pulso medio y máximo), el sueño y los pasos. Si
        un entreno ya estaba por otra vía, no se duplica.
      </p>
    </Section>
  );
}

/** Ajustes → Otros relojes: ficheros, COROS y Health Connect. */
export function OtherWatchesCard() {
  const { data, isPending, isError, refetch } = useSources();
  return (
    <Card id="otros-relojes" className="scroll-mt-20 shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Otros relojes</CardTitle>
        <CardDescription>
          Además de Garmin: importa ficheros, conecta COROS o recibe los datos
          de relojes Android a través de Health Connect.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ImportFiles />
        {isPending ? (
          <Skeleton className="h-40" />
        ) : isError ? (
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => refetch()}
          >
            Reintentar
          </Button>
        ) : (
          <>
            <Coros data={data} />
            <HealthConnect data={data} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
