import { Activity } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** Marco común de las pantallas públicas (login, registro, recuperar contraseña). */
export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-klyp-navy p-4">
      <Card className="w-full max-w-sm shadow-md">
        <CardHeader className="items-center text-center">
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-lg bg-klyp-pale text-klyp-navy">
            <Activity className="size-6" aria-hidden />
          </div>
          <CardTitle className="font-heading text-2xl font-bold">
            {title}
          </CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}

export function FormError({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
    >
      {children}
    </p>
  );
}

export function FormNotice({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      className="rounded-md bg-klyp-pale p-3 text-sm text-klyp-navy"
    >
      {children}
    </p>
  );
}
