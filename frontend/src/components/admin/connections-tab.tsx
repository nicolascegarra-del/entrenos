"use client";

import {
  CircleAlert,
  CircleCheck,
  Copy,
  ExternalLink,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminOuraApp,
  useClearAdminOuraApp,
  useSaveAdminOuraApp,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { OuraAppSettings } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

/** Qué decir sobre el origen de las credenciales. */
export function ouraSourceText(app: OuraAppSettings): string {
  if (app.source === "panel") return "Configurada desde este panel.";
  if (app.source === "entorno")
    return "Configurada con las variables de entorno del servidor. Si guardas aquí, manda lo del panel.";
  return "Sin configurar: tus usuarios ven «Pendiente de configurar».";
}

function CopyRow({ value }: { value: string }) {
  return (
    <li className="flex items-center gap-2">
      <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs">
        {value}
      </code>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="size-11 shrink-0 md:size-8"
        aria-label={`Copiar ${value}`}
        onClick={() =>
          navigator.clipboard
            ?.writeText(value)
            .then(() => toast.success("Copiado."))
            .catch(() => toast.error("No se pudo copiar."))
        }
      >
        <Copy aria-hidden />
      </Button>
    </li>
  );
}

function OuraAppCard({ app }: { app: OuraAppSettings }) {
  const save = useSaveAdminOuraApp();
  const clear = useClearAdminOuraApp();
  const [clientId, setClientId] = useState(app.client_id);
  const [secret, setSecret] = useState("");

  const submit = (newWebhookToken = false) =>
    save.mutate(
      {
        client_id: clientId.trim(),
        client_secret: secret.trim() || null,
        new_webhook_token: newWebhookToken,
      },
      {
        onSuccess: () => {
          setSecret("");
          toast.success(
            newWebhookToken
              ? "Nuevo token de webhooks generado."
              : "Credenciales de Oura guardadas.",
          );
        },
        onError: (err) => toast.error(errorText(err)),
      },
    );

  const canSave =
    !!clientId.trim() && (app.has_secret || !!secret.trim()) && !save.isPending;

  return (
    <section className="space-y-4 rounded-lg border p-4">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 font-semibold">
          Oura Ring
          {app.configured ? (
            <span className="inline-flex items-center gap-1 text-xs font-normal text-emerald-700 dark:text-emerald-400">
              <CircleCheck className="size-4" aria-hidden /> Configurada
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-normal text-amber-700 dark:text-amber-400">
              <CircleAlert className="size-4" aria-hidden /> Sin configurar
            </span>
          )}
        </h2>
        <p className="text-sm text-muted-foreground">{ouraSourceText(app)}</p>
      </header>

      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
        <li>
          Crea la app en{" "}
          <a
            href="https://cloud.ouraring.com/oauth/applications"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-klyp-accent underline"
          >
            cloud.ouraring.com/oauth/applications
            <ExternalLink className="size-3" aria-hidden />
          </a>{" "}
          con tu cuenta de Oura y marca todos los permisos.
        </li>
        <li>Da de alta estas direcciones de vuelta (Redirect URIs):</li>
      </ol>
      <ul className="space-y-1">
        {app.redirect_uris.map((u) => (
          <CopyRow key={u} value={u} />
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        3. Copia aquí el Client ID y el Client Secret que te da Oura. Se guardan
        cifrados y el secreto no se vuelve a mostrar.
      </p>

      <form
        className="grid gap-3 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSave) submit();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="oura-client-id">Client ID</Label>
          <Input
            id="oura-client-id"
            value={clientId}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => setClientId(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="oura-client-secret">Client Secret</Label>
          <Input
            id="oura-client-secret"
            type="password"
            value={secret}
            autoComplete="new-password"
            placeholder={app.has_secret ? "•••••••• (guardado)" : ""}
            onChange={(e) => setSecret(e.target.value)}
          />
          {app.has_secret && (
            <p className="text-xs text-muted-foreground">
              Déjalo vacío para conservar el que hay.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 md:col-span-2">
          <Button
            type="submit"
            className="min-h-11 md:min-h-9"
            disabled={!canSave}
          >
            {save.isPending && <Loader2 className="animate-spin" aria-hidden />}
            Guardar
          </Button>
          {app.source === "panel" && (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 text-destructive md:min-h-9"
              disabled={clear.isPending}
              onClick={() => {
                if (
                  !window.confirm(
                    "¿Quitar las credenciales de Oura del panel? Nadie podrá conectar su anillo hasta que vuelvas a ponerlas (salvo que estén en las variables de entorno).",
                  )
                )
                  return;
                clear.mutate(undefined, {
                  onSuccess: () => {
                    setClientId("");
                    toast.success("Credenciales quitadas.");
                  },
                  onError: (err) => toast.error(errorText(err)),
                });
              }}
            >
              Quitar
            </Button>
          )}
        </div>
      </form>

      <div className="space-y-2 border-t pt-4 text-sm">
        <h3 className="font-medium">Avisos en tiempo real (webhooks)</h3>
        <p className="text-muted-foreground">
          {app.webhooks === "ok"
            ? "Activos: Oura avisa en cuanto el anillo sincroniza. Las suscripciones se crean solas una vez al día."
            : `No activos: ${app.webhooks} Mientras tanto, los datos se traen cada 6 horas.`}
        </p>
        <ul>
          <CopyRow value={app.webhook_url} />
        </ul>
        {app.configured && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 md:min-h-8"
            disabled={save.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "¿Generar un token nuevo para los webhooks? Las suscripciones se volverán a crear en la próxima pasada diaria.",
                )
              )
                submit(true);
            }}
          >
            <RefreshCw aria-hidden /> Nuevo token de webhooks
          </Button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Hasta que Oura apruebe la app, solo pueden conectarse 10 usuarios.
        Puedes limitar quién lo ve en Módulos → Oura Ring.
      </p>
    </section>
  );
}

/** Admin → Conexiones: credenciales de servicios externos (de momento, Oura). */
export function ConnectionsTab() {
  const { data, isPending, isError, refetch } = useAdminOuraApp();
  if (isPending) return <Skeleton className="h-96" />;
  if (isError || !data)
    return (
      <ErrorState
        message="No se pudo cargar la configuración de Oura."
        onRetry={() => refetch()}
      />
    );
  return <OuraAppCard key={data.client_id} app={data} />;
}
