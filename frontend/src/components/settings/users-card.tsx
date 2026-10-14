"use client";

import { Copy, Loader2, Trash2, UserPlus, Users } from "lucide-react";
import { useState } from "react";
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
import {
  useCreateInvitation,
  useDeleteInvitation,
  useInvitations,
  useUsers,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";

const GARMIN_LABEL = {
  none: "Sin Garmin",
  ok: "Garmin conectado",
  expired: "Garmin caducado",
} as const;

/** Gestión de usuarios (solo administrador): cada persona tiene su usuario y su propio Garmin. */
export function UsersCard() {
  const users = useUsers(true);
  const invitations = useInvitations(true);
  const create = useCreateInvitation();
  const remove = useDeleteInvitation();
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Enlace copiado");
    } catch {
      toast.error("No se pudo copiar: selecciónalo y cópialo a mano.");
    }
  };

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Users className="size-5 text-klyp-accent" aria-hidden /> Usuarios
        </CardTitle>
        <CardDescription>
          Invita a otra persona: tendrá su propio usuario, sus datos y su cuenta
          de Garmin.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(email.trim(), {
              onSuccess: (inv) => {
                setLink(
                  `${window.location.origin}/registro?token=${inv.token}`,
                );
                setEmail("");
              },
              onError: (err) =>
                toast.error(
                  err instanceof ApiError ? err.message : "No se pudo invitar.",
                ),
            });
          }}
        >
          <div className="min-w-56 flex-1 space-y-1">
            <Label htmlFor="invite-email">Email de la persona</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 md:h-9"
            />
          </div>
          <Button
            type="submit"
            className="min-h-11 md:min-h-9"
            disabled={!email.trim() || create.isPending}
          >
            {create.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <UserPlus aria-hidden />
            )}{" "}
            Invitar
          </Button>
        </form>

        {link && (
          <div className="space-y-2 rounded-lg border border-klyp-accent/50 bg-klyp-accent/10 p-3 text-sm">
            <p className="font-medium">
              Envíale este enlace (válido 7 días y de un solo uso):
            </p>
            <div className="flex gap-2">
              <Input
                readOnly
                value={link}
                className="h-11 font-mono text-xs md:h-9"
                onFocus={(e) => e.target.select()}
              />
              <Button
                type="button"
                variant="outline"
                className="min-h-11 md:min-h-9"
                onClick={() => copy(link)}
              >
                <Copy aria-hidden /> Copiar
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Por seguridad no se vuelve a mostrar: cópialo ahora.
            </p>
          </div>
        )}

        {!!invitations.data?.length && (
          <div>
            <p className="mb-1 text-sm font-medium">Invitaciones pendientes</p>
            <ul className="space-y-1">
              {invitations.data.map((i) => (
                <li
                  key={i.id}
                  className="flex items-center justify-between gap-2 rounded-md bg-muted/60 px-3 py-1.5 text-sm"
                >
                  <span>
                    {i.email}{" "}
                    <span className="text-xs text-muted-foreground">
                      · caduca {formatDate(i.expires_at)}
                    </span>
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-11 md:size-8"
                    aria-label={`Anular invitación de ${i.email}`}
                    onClick={() => remove.mutate(i.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="mb-1 text-sm font-medium">Usuarios</p>
          <ul className="space-y-1">
            {users.data?.map((u) => (
              <li
                key={u.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 text-sm"
              >
                <span className="break-all">{u.email}</span>
                <span className="flex gap-1">
                  {u.is_admin && (
                    <Badge variant="secondary">Administrador</Badge>
                  )}
                  <Badge variant="outline">{GARMIN_LABEL[u.garmin]}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
