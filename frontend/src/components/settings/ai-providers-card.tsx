"use client";

import {
  CircleCheck,
  ExternalLink,
  KeyRound,
  Loader2,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
  useAiProviders,
  useDeleteAiProvider,
  useSaveAiProvider,
  useTestAiProvider,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { AiProviderRow } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

function StatusBadge({ p }: { p: AiProviderRow }) {
  if (!p.configured) return <Badge variant="outline">Sin configurar</Badge>;
  if (!p.enabled) return <Badge variant="secondary">Desactivado</Badge>;
  if (p.is_default) return <Badge>Predeterminado</Badge>;
  return <Badge variant="secondary">Activo</Badge>;
}

/** Bloque de un proveedor: clave (nunca se muestra), modelo, activar y probar. */
function ProviderBlock({ p }: { p: AiProviderRow }) {
  const [editing, setEditing] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(p.model ?? p.default_model);
  const [enabled, setEnabled] = useState(p.configured ? p.enabled : true);
  const [isDefault, setIsDefault] = useState(p.is_default);
  const [models, setModels] = useState<string[]>([]);
  const save = useSaveAiProvider(p.provider);
  const remove = useDeleteAiProvider(p.provider);
  const test = useTestAiProvider(p.provider);
  const listId = `modelos-${p.provider}`;

  const onSave = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate(
      {
        api_key: apiKey.trim() || null,
        model: model.trim(),
        enabled,
        is_default: isDefault,
      },
      {
        onSuccess: () => {
          setApiKey("");
          setEditing(false);
          toast.success(`${p.label} guardado.`);
        },
        onError: (err) => toast.error(errorText(err)),
      },
    );
  };

  const onTest = () =>
    test.mutate(undefined, {
      onSuccess: (data) => {
        setModels(data.models);
        toast.success(
          `La clave funciona: ${data.models.length} modelos disponibles.`,
        );
      },
      onError: (err) => toast.error(errorText(err)),
    });

  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{p.label}</span>
        <StatusBadge p={p} />
        {p.configured && (
          <span className="text-xs text-muted-foreground tabular-nums">
            clave ••••{p.key_last4} · {p.model}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          className="ml-auto min-h-11 md:min-h-8"
          aria-expanded={editing}
          onClick={() => setEditing((v) => !v)}
        >
          {editing ? "Cerrar" : p.configured ? "Editar" : "Configurar"}
        </Button>
      </div>

      {editing && (
        <form onSubmit={onSave} className="mt-3 space-y-3">
          <p className="text-xs text-muted-foreground">{p.privacy}</p>
          <div className="space-y-1.5">
            <Label htmlFor={`clave-${p.provider}`}>Clave de API</Label>
            <Input
              id={`clave-${p.provider}`}
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                p.configured
                  ? `••••${p.key_last4} (vacía para conservarla)`
                  : "Pega aquí tu clave"
              }
              required={!p.configured}
              minLength={8}
              className="h-11 md:h-9"
            />
            <a
              href={p.keys_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-klyp-accent hover:underline"
            >
              Conseguir una clave{" "}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`modelo-${p.provider}`}>Modelo</Label>
            <Input
              id={`modelo-${p.provider}`}
              list={listId}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              required
              pattern="[A-Za-z0-9._:/\-]{1,100}"
              className="h-11 md:h-9"
            />
            <datalist id={listId}>
              {[...new Set([...p.suggested_models, ...models])].map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <p className="text-xs text-muted-foreground">
              {models.length
                ? "Elige uno de la lista de tu cuenta."
                : `Recomendado: ${p.default_model} (económico). Pulsa «Probar» tras guardar para ver todos los de tu cuenta.`}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <label className="flex min-h-11 items-center gap-2 md:min-h-8">
              <input
                type="checkbox"
                className="size-4 accent-klyp-accent"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Activo
            </label>
            <label className="flex min-h-11 items-center gap-2 md:min-h-8">
              <input
                type="checkbox"
                className="size-4 accent-klyp-accent"
                checked={isDefault}
                disabled={!enabled}
                onChange={(e) => setIsDefault(e.target.checked)}
              />
              Usar por defecto
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              className="min-h-11 md:min-h-9"
              disabled={save.isPending}
            >
              {save.isPending && <Loader2 className="animate-spin" />}
              Guardar
            </Button>
            {p.configured && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 md:min-h-9"
                  onClick={onTest}
                  disabled={test.isPending}
                >
                  {test.isPending ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <CircleCheck aria-hidden />
                  )}
                  Probar conexión
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="min-h-11 text-destructive md:min-h-9"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `¿Quitar ${p.label}? Se borrará la clave guardada.`,
                      )
                    )
                      remove.mutate(undefined, {
                        onSuccess: () => {
                          setEditing(false);
                          toast.success(`${p.label} quitado.`);
                        },
                        onError: (err) => toast.error(errorText(err)),
                      });
                  }}
                >
                  Quitar
                </Button>
              </>
            )}
          </div>
        </form>
      )}
    </li>
  );
}

/**
 * Cuentas de IA del usuario (ChatGPT, Gemini, Claude). Cada persona usa su propia
 * clave de API: se guarda cifrada en el servidor y no vuelve nunca al navegador.
 */
export function AiProvidersCard() {
  const { data, isPending, isError, refetch } = useAiProviders();
  return (
    <Card id="asistente" className="scroll-mt-20 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Sparkles className="size-5 text-klyp-accent" aria-hidden />
          Asistente IA
        </CardTitle>
        <CardDescription>
          Conecta tu cuenta de ChatGPT, Gemini o Claude para preguntar sobre tus
          entrenamientos. Hace falta una <strong>clave de API</strong> (las
          suscripciones Plus/Pro de sus webs no sirven); se guarda cifrada y
          nunca se muestra.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : isError ? (
          <div className="text-sm text-muted-foreground" role="alert">
            No se pudieron cargar los asistentes.{" "}
            <button
              className="font-medium text-klyp-accent underline"
              onClick={() => refetch()}
            >
              Reintentar
            </button>
          </div>
        ) : (
          <>
            <ul className="space-y-2">
              {data.providers.map((p) => (
                <ProviderBlock key={`${p.provider}-${p.updated_at}`} p={p} />
              ))}
            </ul>
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <KeyRound className="size-3.5" aria-hidden />
              Hoy llevas {data.used_today} de {data.daily_limit} preguntas.
              {data.providers.some((p) => p.configured && p.enabled) && (
                <Link
                  href="/asistente"
                  className="font-medium text-klyp-accent hover:underline"
                >
                  Ir al asistente
                </Link>
              )}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
