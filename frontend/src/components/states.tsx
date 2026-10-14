import { AlertTriangle, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-destructive/40 shadow-sm">
      <CardContent
        className="flex flex-col items-center gap-3 py-10 text-center"
        role="alert"
      >
        <AlertTriangle className="size-8 text-destructive" aria-hidden />
        <p className="text-sm text-muted-foreground">{message}</p>
        {onRetry && (
          <Button variant="outline" onClick={onRetry} className="min-h-11">
            Reintentar
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <Card className="shadow-sm">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <div className="flex size-14 items-center justify-center rounded-lg bg-muted text-primary">
          <Icon className="size-7" aria-hidden />
        </div>
        <p className="font-heading text-lg font-semibold">{title}</p>
        {children}
      </CardContent>
    </Card>
  );
}
