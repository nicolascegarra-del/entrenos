"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError, authFetch, parseError } from "@/lib/api";

const FORMATS = [
  { key: "fit", label: "FIT", help: "Garmin, COROS, Wahoo, Suunto, Strava…" },
  { key: "tcx", label: "TCX", help: "Con vueltas: casi todas las apps" },
  { key: "gpx", label: "GPX", help: "Ruta con hora y pulso" },
] as const;

/** Descarga la actividad en FIT, TCX o GPX para llevarla a otra app. */
export function ExportActivity({ activityId }: { activityId: number }) {
  const [busy, setBusy] = useState<string | null>(null);
  const download = async (format: string) => {
    setBusy(format);
    try {
      const res = await authFetch(
        `/api/v1/activities/${activityId}/export?format=${format}`,
      );
      if (!res.ok) throw await parseError(res);
      const name =
        /filename="([^"]+)"/.exec(
          res.headers.get("content-disposition") ?? "",
        )?.[1] ?? `actividad.${format}`;
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo exportar.",
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">
        Exportar para otras apps
      </p>
      <div className="grid grid-cols-3 gap-1.5">
        {FORMATS.map((f) => (
          <Button
            key={f.key}
            variant="outline"
            className="min-h-11 md:min-h-9"
            title={f.help}
            disabled={busy !== null}
            onClick={() => download(f.key)}
          >
            {busy === f.key ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Download aria-hidden />
            )}
            {f.label}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        FIT y TCX llevan vueltas, pulso, cadencia y potencia; GPX, la ruta.
      </p>
    </div>
  );
}
