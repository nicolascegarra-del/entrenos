import { Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  askAboutActivity,
  askAboutProgress,
  askAboutSession,
  askCoachHref,
} from "@/lib/ask-coach";
import type { ActivitySummary } from "@/types/api";

export { askAboutActivity };

/** «Pregúntale al entrenador» con la pregunta ya hecha (se envía al abrir el chat). */
export function AskCoach({
  question,
  label = "Pregúntale al entrenador",
}: {
  question: string;
  label?: string;
}) {
  return (
    <Button asChild variant="outline" size="sm" className="min-h-11 md:min-h-8">
      <Link href={askCoachHref(question)}>
        <Sparkles aria-hidden /> {label}
      </Link>
    </Button>
  );
}

export function AskAi({ activity }: { activity: ActivitySummary }) {
  return <AskCoach question={askAboutActivity(activity)} />;
}

export function AskAboutSession(session: {
  id: number;
  day: string;
  title: string;
}) {
  return <AskCoach question={askAboutSession(session)} />;
}

export function AskAboutProgress({ period }: { period: string }) {
  return <AskCoach question={askAboutProgress(period)} label="Pregúntale" />;
}
