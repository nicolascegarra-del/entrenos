"use client";

import {
  CircleCheck,
  ExternalLink,
  KeyRound,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
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
  useAiModels,
  useAiProviders,
  useDeleteAiProvider,
  useSaveAiProvider,
  useTestAiProvider,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AiProviderRow } from "@/types/api";

const selectClass =
  "h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

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
  const [list, setList] = useState<{
    models: string[];
    recommended: string[];
  } | null>(null);
  const save = useSaveAiProvider(p.provider);
  const remove = useDeleteAiProvider(p.provider);
  const test = useTestAiProvider(p.provider);
  const loadModels = useAiModels(p.provider);
  const { mutate: fetchModels } = loadModels;

  const load = (key: string | null) =>
    fetchModels(key, {
      onSuccess: (data) => setList(data),
      onError: (err) => toast.error(errorText(err)),
    });

  // Con una cuenta guardada, la lista se pide al abrir el formulario.
  useEffect(() => {
    if (editing && p.configured && !list) load(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const known = list ? [...list.recommended, ...list.models] : [];
  const fallback = [...new Set([model, ...p.suggested_models])];

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
        toast.success(
          `Todo correcto: ${data.model} responde (${data.models.length} modelos en tu cuenta).`,
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
            <div className="flex gap-2">
              <select
                id={`modelo-${p.provider}`}
                className={selectClass}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={loadModels.isPending}
              >
                {list ? (
                  <>
                    {!known.includes(model) && (
                      <option value={model}>
                        {model} (actual · ya no aparece en tu cuenta)
                      </option>
                    )}
                    {list.recommended.length > 0 && (
                      <optgroup label="Recomendados">
                        {list.recommended.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    <optgroup label="Todos los de tu cuenta">
                      {list.models.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </optgroup>
                  </>
                ) : (
                  fallback.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))
                )}
              </select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="size-11 shrink-0 md:size-9"
                aria-label="Actualizar la lista de modelos"
                title="Actualizar la lista de modelos"
                disabled={
                  loadModels.isPending ||
                  (!p.configured && apiKey.trim().length < 8)
                }
                onClick={() => load(apiKey.trim() || null)}
              >
                <RefreshCw
                  className={cn(loadModels.isPending && "animate-spin")}
                />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {loadModels.isPending
                ? "Cargando los modelos de tu cuenta…"
                : list
                  ? "Lista de tu cuenta. Al guardar se comprueba que el modelo responde."
                  : p.configured
                    ? "Pulsa ⟳ para ver los modelos de tu cuenta."
                    : "Pega la clave y pulsa ⟳ para ver los modelos de tu cuenta."}
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
              {save.isPending ? "Comprobando…" : "Guardar"}
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
