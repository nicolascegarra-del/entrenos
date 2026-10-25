"use client";

import {
  AlertTriangle,
  RefreshCw,
  StepForward,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useMessageFeedback } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import type { CoachEffect } from "@/types/api";

/** Botones de respuesta rápida (a la pregunta del entrenador) o de sugerencias para seguir hablando. */
export function ReplyChips({
  effects,
  disabled,
  onPick,
}: {
  effects?: CoachEffect[];
  disabled: boolean;
  onPick: (text: string) => void;
}) {
  const options = effects?.find((e) => e.tipo === "opciones");
  const suggestions = effects?.find((e) => e.tipo === "sugerencias");
  const items =
    options?.tipo === "opciones"
      ? options.opciones
      : suggestions?.tipo === "sugerencias"
        ? suggestions.sugerencias
        : [];
  if (!items.length) return null;
  const answer = !!options;
  return (
    <div
      className="flex flex-wrap gap-2"
      role="group"
      aria-label={answer ? "Respuestas rápidas" : "Para seguir"}
    >
      {items.map((item) => (
        <button
          key={item}
          type="button"
          disabled={disabled}
          onClick={() => onPick(item)}
          className={cn(
            "min-h-11 rounded-full border px-3 py-1.5 text-left text-sm transition-colors disabled:opacity-50 md:min-h-9",
            answer
              ? "border-klyp-accent bg-klyp-accent/10 font-medium text-foreground hover:bg-klyp-accent/20"
              : "hover:bg-muted",
          )}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

/** 👍 / 👎 y «Otra respuesta» bajo la última respuesta del entrenador. */
export function MessageActions({
  id,
  feedback,
  last,
  disabled,
  onRegenerate,
}: {
  id: number;
  feedback?: number | null;
  last: boolean;
  disabled: boolean;
  onRegenerate: () => void;
}) {
  const rate = useMessageFeedback();
  const value =
    rate.variables?.id === id && rate.isPending
      ? rate.variables.value
      : feedback;
  const set = (v: -1 | 1) => rate.mutate({ id, value: value === v ? 0 : v });
  return (
    <div className="mt-1 flex items-center gap-0.5 text-muted-foreground">
      <Button
        variant="ghost"
        size="icon"
        className={cn("size-9 md:size-7", value === 1 && "text-klyp-accent")}
        aria-label="Me ha servido"
        aria-pressed={value === 1}
        onClick={() => set(1)}
      >
        <ThumbsUp className="size-4" aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className={cn("size-9 md:size-7", value === -1 && "text-destructive")}
        aria-label="No me ha servido"
        aria-pressed={value === -1}
        onClick={() => set(-1)}
      >
        <ThumbsDown className="size-4" aria-hidden />
      </Button>
      {last && (
        <Button
          variant="ghost"
          size="sm"
          className="min-h-9 gap-1 px-2 text-xs md:min-h-7"
          disabled={disabled}
          onClick={onRegenerate}
        >
          <RefreshCw className="size-3.5" aria-hidden /> Otra respuesta
        </Button>
      )}
    </div>
  );
}

/** El entrenador no ha podido responder: el motivo y cómo seguir, dentro del chat (no un aviso que se escapa). */
export function FailureBubble({
  message,
  partial,
  disabled,
  onRetry,
  onContinue,
}: {
  message: string;
  partial: boolean;
  disabled: boolean;
  onRetry: () => void;
  onContinue: () => void;
}) {
  return (
    <div
      role="alert"
      className="max-w-[90%] space-y-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 md:max-w-[75%] dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
    >
      <p className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          {partial
            ? "La respuesta se ha cortado. Te he guardado lo que llevaba."
            : "No he podido responder."}{" "}
          <span className="opacity-80">({message})</span>
        </span>
      </p>
      <div className="flex flex-wrap gap-2">
        {partial && (
          <Button
            size="sm"
            className="min-h-11 md:min-h-8"
            disabled={disabled}
            onClick={onContinue}
          >
            <StepForward aria-hidden /> Continuar
          </Button>
        )}
        <Button
          size="sm"
          variant={partial ? "outline" : "default"}
          className="min-h-11 md:min-h-8"
          disabled={disabled}
          onClick={onRetry}
        >
          <RefreshCw aria-hidden /> Reintentar
        </Button>
      </div>
    </div>
  );
}
