"use client";

import {
  NotebookPen,
  Pencil,
  Plus,
  Trash2,
  UserRoundSearch,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCoachMemories,
  useCoachSettings,
  useSaveCoachMemory,
  useSaveCoachSettings,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CoachMemory } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo guardar.";

const SOURCE: Record<CoachMemory["source"], string> = {
  ia: "lo apuntó la IA",
  usuario: "lo añadiste tú",
  entrevista: "de la entrevista",
  revision: "de una revisión",
};

const selectClass =
  "h-11 rounded-md border border-input bg-background px-2 text-sm md:h-9";

function MemoryRow({
  memory,
  categories,
}: {
  memory: CoachMemory;
  categories: Record<string, string>;
}) {
  const save = useSaveCoachMemory();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(memory.content);
  return (
    <li className="flex items-start gap-2 rounded-md border p-2 text-sm">
      {editing ? (
        <form
          className="flex min-w-0 flex-1 flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              { id: memory.id, category: memory.category, content: text },
              {
                onSuccess: () => setEditing(false),
                onError: (err) => toast.error(errorText(err)),
              },
            );
          }}
        >
          <Input
            aria-label="Dato"
            className="h-11 min-w-0 flex-1 md:h-9"
            value={text}
            maxLength={500}
            onChange={(e) => setText(e.target.value)}
          />
          <Button
            type="submit"
            className="min-h-11 md:min-h-9"
            disabled={save.isPending}
          >
            Guardar
          </Button>
        </form>
      ) : (
        <span className="min-w-0 flex-1">
          {memory.content}
          <span className="block text-xs text-muted-foreground">
            {categories[memory.category] ?? memory.category} ·{" "}
            {SOURCE[memory.source]} · {formatDate(memory.created_at)}
          </span>
        </span>
      )}
      {!editing && (
        <Button
          variant="ghost"
          size="icon"
          className="size-11 shrink-0 md:size-8"
          aria-label="Corregir"
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden />
        </Button>
      )}
      <Button
        variant="ghost"
        size="icon"
        className="size-11 shrink-0 text-destructive md:size-8"
        aria-label="Borrar"
        disabled={save.isPending}
        onClick={() =>
          save.mutate(
            { id: memory.id, remove: true },
            { onError: (err) => toast.error(errorText(err)) },
          )
        }
      >
        <Trash2 aria-hidden />
      </Button>
    </li>
  );
}

/** Ajustes → Asistente IA: «Lo que sé de ti» (ficha del entrenador), consentimiento y revisión semanal. */
export function CoachCard() {
  const { data: settings } = useCoachSettings();
  const { data: memories, isPending } = useCoachMemories();
  const saveSettings = useSaveCoachSettings();
  const save = useSaveCoachMemory();
  const [category, setCategory] = useState("disponibilidad");
  const [text, setText] = useState("");
  const categories = settings?.categories ?? {};
  const allowed = Object.keys(categories).filter(
    (c) => settings?.health_consent || !settings?.health_categories.includes(c),
  );
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <NotebookPen className="size-5 text-klyp-accent" aria-hidden /> Lo que
          sé de ti
        </CardTitle>
        <CardDescription>
          Tu entrenador IA recuerda lo que le cuentas (historial, lesiones,
          disponibilidad, preferencias…) y lo tiene en cuenta en cada respuesta.
          Aquí lo ves, lo corriges o lo borras.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!settings ? (
          <Skeleton className="h-24" />
        ) : (
          <div className="space-y-2">
            <label className="flex min-h-11 cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-0.5 size-5"
                checked={settings.health_consent}
                disabled={saveSettings.isPending}
                onChange={(e) => {
                  if (
                    !e.target.checked &&
                    !window.confirm(
                      "¿Quitar el permiso? Se borrarán las lesiones y datos de salud guardados.",
                    )
                  )
                    return;
                  saveSettings.mutate({ health_consent: e.target.checked });
                }}
              />
              <span className="text-sm">
                <span className="block font-medium">
                  Puede guardar lesiones y datos de salud
                </span>
                <span className="block text-muted-foreground">
                  Lesiones, enfermedades o medicación (p. ej. un betabloqueante
                  cambia la lectura del pulso). Solo se envían a tu propio
                  asistente de IA y puedes borrarlos cuando quieras.
                </span>
              </span>
            </label>
            <label className="flex min-h-11 cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-0.5 size-5"
                checked={settings.weekly_review}
                disabled={saveSettings.isPending}
                onChange={(e) =>
                  saveSettings.mutate({ weekly_review: e.target.checked })
                }
              />
              <span className="text-sm">
                <span className="block font-medium">Revisión semanal</span>
                <span className="block text-muted-foreground">
                  El domingo por la tarde te pregunta qué tal la semana y te
                  dice qué toca. El aviso al móvil se gestiona en
                  Notificaciones.
                </span>
              </span>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button
                asChild
                variant={settings.interview_done ? "outline" : "default"}
                className="min-h-11 md:min-h-9"
              >
                <Link href="/asistente?modo=entrevista">
                  <UserRoundSearch aria-hidden />
                  {settings.interview_done
                    ? "Repetir la entrevista"
                    : "Hacer la entrevista inicial"}
                </Link>
              </Button>
              <Button asChild variant="ghost" className="min-h-11 md:min-h-9">
                <Link href="/asistente/semana">Revisión de esta semana</Link>
              </Button>
            </div>
          </div>
        )}

        {isPending ? (
          <Skeleton className="h-24" />
        ) : !memories?.length ? (
          <p className="rounded-lg bg-muted/60 p-3 text-sm">
            Aún no sé nada de ti más allá de tu reloj. Haz la entrevista inicial
            o cuéntamelo en el chat.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {memories.map((m) => (
              <MemoryRow key={m.id} memory={m} categories={categories} />
            ))}
          </ul>
        )}

        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              { category, content: text },
              {
                onSuccess: () => setText(""),
                onError: (err) => toast.error(errorText(err)),
              },
            );
          }}
        >
          <select
            aria-label="Categoría"
            className={selectClass}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {allowed.map((c) => (
              <option key={c} value={c}>
                {categories[c]}
              </option>
            ))}
          </select>
          <Input
            aria-label="Nuevo dato"
            placeholder="Ej. Solo puedo entrenar martes, jueves y sábado"
            className="h-11 min-w-0 flex-1 md:h-9"
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button
            type="submit"
            variant="outline"
            className="min-h-11 md:min-h-9"
            disabled={!text.trim() || save.isPending}
          >
            <Plus aria-hidden /> Añadir
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
