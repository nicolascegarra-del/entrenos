"use client";

import { SendHorizontal, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAiProviders } from "@/hooks/use-api";
import { askCoachHref, todaySuggestions } from "@/lib/ask-coach";
import type { Summary } from "@/types/api";

/** Hoy: pregunta a tu entrenador sin salir de aquí, con preguntas sugeridas según tu día. */
export function AskCoachCard({
  summary,
  today,
}: {
  summary: Pick<Summary, "planned_this_week" | "readiness">;
  today: string;
}) {
  const router = useRouter();
  const { data: ai } = useAiProviders();
  const [text, setText] = useState("");
  if (!ai) return null;
  const hasAi = ai.providers.some((p) => p.configured && p.enabled);
  if (!hasAi)
    return (
      <Link
        href="/ajustes/asistente"
        className="flex min-h-11 items-center gap-3 rounded-lg border border-dashed p-3 text-sm hover:bg-muted/60"
      >
        <Sparkles className="size-5 shrink-0 text-klyp-accent" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">Ten tu entrenador personal</span>
          <span className="text-muted-foreground">
            Conecta tu IA (ChatGPT, Gemini o Claude) y pregúntale lo que quieras
            con todos tus datos.
          </span>
        </span>
      </Link>
    );

  const ask = (q: string) => {
    if (q.trim()) router.push(askCoachHref(q.trim()));
  };
  return (
    <div
      className="space-y-2 rounded-lg border bg-card p-3 shadow-sm"
      data-tour="ask-coach"
    >
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <Sparkles className="size-5 shrink-0 text-klyp-accent" aria-hidden />
        <label htmlFor="pregunta-hoy" className="sr-only">
          Pregúntale a tu entrenador
        </label>
        <input
          id="pregunta-hoy"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          placeholder="Pregúntale a tu entrenador…"
          enterKeyHint="send"
          className="h-11 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-base shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9 md:text-sm"
        />
        <Button
          type="submit"
          size="icon"
          className="size-11 md:size-9"
          aria-label="Preguntar"
          disabled={!text.trim()}
        >
          <SendHorizontal className="size-4" aria-hidden />
        </Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {todaySuggestions(summary, today).map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => ask(q)}
            className="min-h-11 rounded-full border px-3 text-left text-sm hover:bg-muted/60 md:min-h-8"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
