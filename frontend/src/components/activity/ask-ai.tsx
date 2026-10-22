import { Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import type { ActivitySummary } from "@/types/api";

/** Pregunta preparada para que el asistente analice esta actividad (con su id para consultar el detalle). */
export function askAboutActivity(
  a: Pick<ActivitySummary, "id" | "name" | "start_time">,
): string {
  return (
    `Analiza mi entreno «${a.name || "sin nombre"}» del ${formatDate(a.start_time)} (id ${a.id}): ` +
    "ritmo, pulso, zonas, vueltas y sensaciones. ¿Qué tal fue y qué me recomiendas?"
  );
}

export function AskAi({ activity }: { activity: ActivitySummary }) {
  return (
    <Button asChild variant="outline" size="sm" className="min-h-11 md:min-h-8">
      <Link
        href={`/asistente?q=${encodeURIComponent(askAboutActivity(activity))}`}
      >
        <Sparkles aria-hidden /> Pregúntale a la IA
      </Link>
    </Button>
  );
}
