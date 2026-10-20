"use client";

import { Loader2, MailPlus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CopyLink } from "@/components/admin/copy-link";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminInvitations,
  useAdminSettings,
  useInvitationAction,
} from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { InvitationCreated, InvitationRow } from "@/types/api";

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo completar la operación.";

const STATUS = {
  pending: { label: "Pendiente", variant: "default" },
  used: { label: "Usada", variant: "secondary" },
  expired: { label: "Caducada", variant: "outline" },
} as const;

const selectClass =
  "h-11 rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-9";

const DAYS = [1, 3, 7, 14, 30];

function InvitationItem({
  inv,
  onLink,
}: {
  inv: InvitationRow;
  onLink: (c: InvitationCreated) => void;
}) {
  const action = useInvitationAction();
  const { label, variant } = STATUS[inv.status];
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{inv.email}</span>
        <span className="block text-xs text-muted-foreground">
          {inv.status === "used"
            ? `Usada ${formatDateTime(inv.used_at!)}${inv.used_by_email ? ` por ${inv.used_by_email}` : ""}`
            : `${inv.status === "expired" ? "Caducó" : "Caduca"} ${formatDateTime(inv.expires_at)}`}
        </span>
      </span>
      <Badge variant={variant}>{label}</Badge>
      {inv.status !== "used" && (
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 md:min-h-8"
          disabled={action.isPending}
          onClick={() =>
            action.mutate(
              { path: `/${inv.id}/renew`, body: { days: 7 } },
              {
                onSuccess: (data) => {
                  onLink(data as InvitationCreated);
                  toast.success("Enlace nuevo generado (7 días).");
                },
                onError: (err) => toast.error(errorText(err)),
              },
            )
          }
        >
          <RefreshCw aria-hidden /> Renovar
        </Button>
      )}
      <Button
        size="icon"
        variant="ghost"
        className="size-11 text-muted-foreground md:size-8"
        aria-label={`Anular la invitación de ${inv.email}`}
        onClick={() => {
          if (!window.confirm(`¿Anular la invitación de ${inv.email}?`)) return;
          action.mutate(
            { path: `/${inv.id}`, method: "DELETE" },
            { onError: (err) => toast.error(errorText(err)) },
          );
        }}
      >
        <Trash2 className="size-4" />
      </Button>
    </li>
  );
}

/** Invitaciones: crear (con caducidad y envío por email), renovar y anular. */
export function InvitationsTab() {
  const { data, isPending, isError, refetch } = useAdminInvitations();
  const { data: settings } = useAdminSettings();
  const create = useInvitationAction();
  const [email, setEmail] = useState("");
  const [days, setDays] = useState(7);
  const [sendEmail, setSendEmail] = useState(true);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const emailEnabled = !!settings?.email_enabled;

  return (
    <div className="space-y-4">
      <form
        className="space-y-3 rounded-lg border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            {
              body: {
                email,
                days,
                send_email: emailEnabled && sendEmail,
              },
            },
            {
              onSuccess: (data) => {
                setCreated(data as InvitationCreated);
                setEmail("");
              },
              onError: (err) => toast.error(errorText(err)),
            },
          );
        }}
      >
        <p className="font-medium">Invitar a una persona</p>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="inv-email">Email</Label>
            <Input
              id="inv-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 md:h-9"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="inv-days">Caduca en</Label>
            <select
              id="inv-days"
              className={selectClass}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              {DAYS.map((d) => (
                <option key={d} value={d}>
                  {d} {d === 1 ? "día" : "días"}
                </option>
              ))}
            </select>
          </div>
        </div>
        {emailEnabled ? (
          <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-8">
            <input
              type="checkbox"
              className="size-4 accent-klyp-accent"
              checked={sendEmail}
              onChange={(e) => setSendEmail(e.target.checked)}
            />
            Enviarla también por email
          </label>
        ) : (
          <p className="text-xs text-muted-foreground">
            No hay correo configurado: tendrás que copiar el enlace y enviárselo
            tú.
          </p>
        )}
        <Button
          type="submit"
          className="min-h-11 md:min-h-9"
          disabled={create.isPending || !email}
        >
          {create.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <MailPlus aria-hidden />
          )}
          Crear invitación
        </Button>
        {created && (
          <CopyLink
            link={created.link}
            expiresAt={created.expires_at}
            emailed={created.emailed}
            onClose={() => setCreated(null)}
          />
        )}
      </form>

      {isPending ? (
        <Skeleton className="h-24" />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar las invitaciones."
          onRetry={() => refetch()}
        />
      ) : !data.length ? (
        <p className="text-center text-sm text-muted-foreground">
          Aún no has invitado a nadie.
        </p>
      ) : (
        <ul className="space-y-2">
          {data.map((inv) => (
            <InvitationItem key={inv.id} inv={inv} onLink={setCreated} />
          ))}
        </ul>
      )}
    </div>
  );
}
