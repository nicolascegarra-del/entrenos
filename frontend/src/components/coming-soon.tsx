import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

interface ComingSoonProps {
  title: string;
  description: string;
  phase: string;
  icon: LucideIcon;
}

/** Estado vacío para secciones que llegan en fases posteriores del roadmap. */
export function ComingSoon({
  title,
  description,
  phase,
  icon: Icon,
}: ComingSoonProps) {
  return (
    <section className="space-y-4">
      <h1 className="font-heading text-2xl font-bold text-foreground md:text-3xl">
        {title}
      </h1>
      <Card className="shadow-sm">
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <div className="flex size-14 items-center justify-center rounded-lg bg-muted text-primary">
            <Icon className="size-7" aria-hidden />
          </div>
          <p className="max-w-md text-sm text-muted-foreground md:text-base">
            {description}
          </p>
          <span className="rounded-md bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground">
            {phase}
          </span>
        </CardContent>
      </Card>
    </section>
  );
}
