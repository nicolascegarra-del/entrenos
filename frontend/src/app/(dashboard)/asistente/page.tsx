"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  History,
  MessageSquarePlus,
  SendHorizontal,
  Sparkles,
  Square,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Consulted } from "@/components/assistant/consulted";
import { Markdown } from "@/components/assistant/markdown";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAiProviders,
  useConversation,
  useConversations,
  useDeleteConversation,
} from "@/hooks/use-api";
import { ApiError, apiFetch } from "@/lib/api";
import { streamChat } from "@/lib/chat-stream";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AiProviderId, Conversation } from "@/types/api";

const SUGGESTIONS = [
  "Analiza mi último entreno: ritmo, pulso, zonas y vueltas",
  "¿Estoy mejorando el ritmo a igual pulso este último mes?",
  "¿Cómo llego hoy y qué me recomiendas entrenar?",
  "¿Voy bien para mi objetivo? ¿Qué debería mejorar?",
  "¿Cuánto tiempo paso en cada zona de pulso? ¿Hago suficiente rodaje suave?",
];

interface Bubble {
  key: string;
  role: "user" | "assistant";
  content: string;
  /** Datos que consultó el asistente. */
  tools?: string[];
}

const selectClass =
  "h-11 rounded-md border border-input bg-background px-2 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

function ConversationList({
  current,
  onPick,
}: {
  current: number | null;
  onPick: (id: number | null) => void;
}) {
  const { data, isPending } = useConversations();
  const remove = useDeleteConversation();
  return (
    <div className="flex min-h-0 flex-col gap-2">
      <Button
        variant="outline"
        className="min-h-11 justify-start md:min-h-9"
        onClick={() => onPick(null)}
      >
        <MessageSquarePlus aria-hidden /> Nueva conversación
      </Button>
      {isPending ? (
        <Skeleton className="h-24" />
      ) : !data?.length ? (
        <p className="px-1 text-sm text-muted-foreground">
          Aún no hay conversaciones.
        </p>
      ) : (
        <ul className="space-y-1 overflow-y-auto">
          {data.map((c) => (
            <li key={c.id} className="group flex items-center gap-1">
              <button
                type="button"
                onClick={() => onPick(c.id)}
                aria-current={c.id === current ? "true" : undefined}
                className={cn(
                  "min-h-11 min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                  c.id === current && "bg-muted font-medium",
                )}
              >
                <span className="block truncate">{c.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {formatDateTime(c.updated_at)}
                </span>
              </button>
              <Button
                variant="ghost"
                size="icon"
                className="size-11 shrink-0 text-muted-foreground md:size-9"
                aria-label={`Borrar «${c.title}»`}
                onClick={() => {
                  if (!window.confirm("¿Borrar esta conversación?")) return;
                  remove.mutate(c.id, {
                    onSuccess: () => c.id === current && onPick(null),
                  });
                }}
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AssistantChat() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const { data: ai, isPending: loadingAi } = useAiProviders();
  const [conversationId, setConversationId] = useState<number | null>(() => {
    const c = Number(params.get("c"));
    return Number.isInteger(c) && c > 0 ? c : null;
  });
  const { data: conversation, isFetching } = useConversation(conversationId);
  const [pending, setPending] = useState<Bubble[]>([]);
  const [input, setInput] = useState(params.get("q") ?? "");
  const [provider, setProvider] = useState<AiProviderId | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const active = ai?.providers.filter((p) => p.configured && p.enabled) ?? [];
  const chosen =
    provider ??
    active.find((p) => p.is_default)?.provider ??
    active[0]?.provider;

  const saved: Bubble[] =
    conversation?.messages.map((m) => ({
      key: `m${m.id}`,
      role: m.role,
      content: m.content,
      tools: m.tools ?? [],
    })) ?? [];
  const bubbles = [...saved, ...pending];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [bubbles.length, pending]);

  const pick = (id: number | null) => {
    abortRef.current?.abort();
    setPending([]);
    setConversationId(id);
    setHistoryOpen(false);
    router.replace(id ? `/asistente?c=${id}` : "/asistente");
  };

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || streaming) return;
    setInput("");
    setStreaming(true);
    setPending([
      { key: "u-pending", role: "user", content: message },
      { key: "a-pending", role: "assistant", content: "", tools: [] },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    let currentId = conversationId;
    try {
      await streamChat(
        { message, conversation_id: conversationId, provider: chosen },
        {
          onMeta: (meta) => {
            currentId = meta.conversation_id;
          },
          onDelta: (delta) =>
            setPending((prev) =>
              prev.map((b) =>
                b.key === "a-pending"
                  ? { ...b, content: b.content + delta }
                  : b,
              ),
            ),
          onTool: (label) =>
            setPending((prev) =>
              prev.map((b) =>
                b.key === "a-pending"
                  ? { ...b, tools: [...(b.tools ?? []), label] }
                  : b,
              ),
            ),
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        toast.error(
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "No se pudo obtener respuesta.",
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      if (currentId) {
        // Se carga la conversación guardada antes de quitar las burbujas provisionales (sin parpadeo).
        await queryClient
          .fetchQuery({
            queryKey: ["conversation", currentId],
            queryFn: () =>
              apiFetch<Conversation>(`/api/v1/chat/conversations/${currentId}`),
            staleTime: 0,
          })
          .catch(() => undefined);
        if (currentId !== conversationId) {
          setConversationId(currentId);
          router.replace(`/asistente?c=${currentId}`);
        }
      }
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      await queryClient.invalidateQueries({ queryKey: ["ai-providers"] });
      setPending([]);
    }
  };

  if (loadingAi) return <Skeleton className="h-64 w-full" />;

  if (!active.length) {
    return (
      <EmptyState icon={Sparkles} title="Conecta un asistente de IA">
        <p className="max-w-sm text-sm text-muted-foreground">
          Añade tu clave de ChatGPT, Gemini o Claude en{" "}
          <Link
            href="/ajustes/asistente"
            className="font-medium text-klyp-accent underline"
          >
            Ajustes
          </Link>{" "}
          y podrás preguntar sobre tus entrenamientos.
        </p>
      </EmptyState>
    );
  }

  return (
    <div className="lg:grid lg:grid-cols-[16rem_1fr] lg:gap-6">
      <aside className="hidden lg:block">
        <ConversationList current={conversationId} onPick={pick} />
      </aside>

      {/* Alto disponible: pantalla menos cabecera, título y barra inferior (móvil). */}
      <div className="flex h-[calc(100dvh-12rem-env(safe-area-inset-bottom))] min-h-80 flex-col rounded-lg border bg-card shadow-sm lg:h-[calc(100dvh-9rem)]">
        <div className="flex items-center gap-2 border-b p-2">
          <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="min-h-11 lg:hidden">
                <History aria-hidden /> Conversaciones
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-80 p-4">
              <SheetTitle>Conversaciones</SheetTitle>
              <ConversationList current={conversationId} onPick={pick} />
            </SheetContent>
          </Sheet>
          <span className="hidden truncate text-sm font-medium lg:block">
            {conversation?.title ?? "Nueva conversación"}
          </span>
          <label className="ml-auto flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <span className="sr-only sm:not-sr-only">Asistente</span>
            <select
              className={cn(
                selectClass,
                "max-w-44 min-w-0 truncate sm:max-w-none",
              )}
              value={chosen}
              onChange={(e) => setProvider(e.target.value as AiProviderId)}
              disabled={streaming}
            >
              {active.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {p.label.split(" ")[0]} · {p.model}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div
          className="flex-1 space-y-3 overflow-y-auto p-3 md:p-4"
          aria-live="polite"
        >
          {conversationId && isFetching && !conversation ? (
            <Skeleton className="h-24" />
          ) : bubbles.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <Sparkles className="size-8 text-klyp-accent" aria-hidden />
              <div>
                <p className="font-heading text-lg font-semibold">
                  Pregúntame por tus entrenamientos
                </p>
                <p className="text-sm text-muted-foreground">
                  Consulto todos tus datos sincronizados (cada entreno con sus
                  vueltas, pulso y zonas, tu progresión, salud, plan y
                  objetivos) y te explico en qué me baso.
                </p>
              </div>
              <ul className="flex max-w-xl flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      onClick={() => send(s)}
                      className="min-h-11 rounded-full border px-3 py-1.5 text-sm hover:bg-muted md:min-h-8"
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            bubbles.map((b) => (
              <div
                key={b.key}
                className={cn(
                  "max-w-[90%] rounded-lg px-3 py-2 text-sm md:max-w-[75%]",
                  b.role === "user"
                    ? "ml-auto bg-klyp-accent text-white"
                    : "bg-muted",
                )}
              >
                {b.role === "assistant" ? (
                  <>
                    <Consulted
                      labels={b.tools ?? []}
                      working={b.key === "a-pending" && streaming}
                    />
                    {b.content && <Markdown text={b.content} />}
                  </>
                ) : (
                  <p className="whitespace-pre-wrap">{b.content}</p>
                )}
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>

        <form
          className="border-t p-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <div className="flex items-end gap-2">
            <label htmlFor="pregunta" className="sr-only">
              Tu pregunta
            </label>
            <textarea
              id="pregunta"
              rows={1}
              value={input}
              maxLength={2000}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              placeholder="Escribe tu pregunta…"
              className="max-h-32 min-h-11 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2.5 text-base shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:text-sm"
            />
            {streaming ? (
              <Button
                type="button"
                size="icon"
                variant="outline"
                className="size-11"
                aria-label="Detener"
                onClick={() => abortRef.current?.abort()}
              >
                <Square className="size-4" />
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                className="size-11"
                aria-label="Enviar"
                disabled={!input.trim()}
              >
                <SendHorizontal className="size-4" />
              </Button>
            )}
          </div>
          <p className="mt-1 px-1 text-[11px] text-muted-foreground">
            Respuestas generadas por IA con tus datos; pueden equivocarse y no
            son consejo médico.
            {ai && ` Hoy: ${ai.used_today}/${ai.daily_limit}.`}
          </p>
        </form>
      </div>
    </div>
  );
}

/** Chat con el asistente de IA sobre los entrenamientos del usuario. */
export default function AsistentePage() {
  return (
    <section className="space-y-3 md:space-y-4">
      <h1 className="flex items-center gap-2 font-heading text-2xl font-bold md:text-3xl">
        <Sparkles className="size-6 text-klyp-accent" aria-hidden />
        Asistente IA
      </h1>
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <AssistantChat />
      </Suspense>
    </section>
  );
}
