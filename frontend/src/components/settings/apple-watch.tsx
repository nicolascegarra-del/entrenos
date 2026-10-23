"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  FileArchive,
  Loader2,
  Repeat,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  CopyRow,
  PersonalToken,
  Section,
} from "@/components/settings/watch-sources";
import { Button } from "@/components/ui/button";
import { useAppleImport, useSources } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { isAppleExport, uploadAppleExport } from "@/lib/apple-upload";
import { formatDateTime } from "@/lib/format";

type Sources = NonNullable<ReturnType<typeof useSources>["data"]>;

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : "No se pudo subir el fichero.";

function Bar({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className="h-2 overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full bg-klyp-accent transition-[width]"
        style={{ width: `${value}%` }}
      />
    </div>
  );
}

/** Historial completo: subir el export.zip de Salud y seguir su procesado. */
function AppleExport() {
  const input = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();
  const { data: last } = useAppleImport();
  const [upload, setUpload] = useState<{ name: string; pct: number } | null>(
    null,
  );

  const run = async (file: File) => {
    if (!isAppleExport(file.name)) {
      toast.error("Sube el export.zip de la app Salud (o su export.xml).");
      return;
    }
    abort.current = new AbortController();
    setUpload({ name: file.name, pct: 0 });
    try {
      await uploadAppleExport(
        file,
        (f) => setUpload({ name: file.name, pct: f * 100 }),
        abort.current.signal,
      );
      toast.success("Subido. Ahora se procesa: puedes cerrar esta página.");
    } catch (err) {
      if (!abort.current.signal.aborted) toast.error(errorText(err));
    } finally {
      setUpload(null);
      queryClient.invalidateQueries({ queryKey: ["apple-import"] });
    }
  };

  const working =
    last && (last.status === "queued" || last.status === "processing");
  return (
    <Section icon={FileArchive} title="Tu historial (export de Salud)">
      <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
        <li>
          En el iPhone, abre la app <strong>Salud</strong> → tu foto (arriba a
          la derecha) → <strong>Exportar todos los datos de salud</strong>.
          Tarda unos minutos.
        </li>
        <li>
          Guarda el <code className="rounded bg-muted px-1">export.zip</code> en
          Archivos (o pásalo al ordenador por AirDrop).
        </li>
        <li>Súbelo aquí tal cual, sin descomprimir.</li>
      </ol>
      <input
        ref={input}
        type="file"
        accept=".zip,.xml,application/zip,text/xml"
        className="sr-only"
        aria-label="Export de Apple Salud"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) run(file);
          e.target.value = "";
        }}
      />
      {upload ? (
        <div className="space-y-1.5" role="status">
          <p className="text-sm">
            Subiendo {upload.name}… {Math.floor(upload.pct)} %
          </p>
          <Bar value={upload.pct} label="Subida del export" />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs text-muted-foreground">
              No cierres esta página hasta que termine la subida.
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 md:min-h-8"
              onClick={() => abort.current?.abort()}
            >
              <X aria-hidden /> Cancelar
            </Button>
          </div>
        </div>
      ) : working ? (
        <div className="space-y-1.5" role="status">
          <p className="flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {last.status === "queued"
              ? "En cola para procesar…"
              : `Leyendo tu historial… ${last.progress} %`}
          </p>
          <Bar value={last.progress} label="Procesado del export" />
          <p className="text-xs text-muted-foreground">
            Con años de datos puede tardar varios minutos. Sigue en segundo
            plano aunque cierres la app.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {last?.status === "done" && (
            <p className="flex items-start gap-2 text-sm">
              <CircleCheck
                className="mt-0.5 size-4 shrink-0 text-emerald-600"
                aria-hidden
              />
              <span>
                {formatDateTime(last.created_at)}:{" "}
                <strong>
                  {last.result.workouts ?? 0}{" "}
                  {last.result.workouts === 1
                    ? "entreno nuevo"
                    : "entrenos nuevos"}
                </strong>
                {last.result.duplicates
                  ? `, ${last.result.duplicates} ya estaban (no se duplican)`
                  : ""}
                {last.result.days
                  ? ` y ${last.result.days} ${last.result.days === 1 ? "día" : "días"} con FC en reposo, sueño o pasos`
                  : ""}
                .{" "}
                {(last.result.workouts ?? 0) > 0 && (
                  <Link
                    href="/actividades"
                    className="text-klyp-accent underline"
                  >
                    Ver entrenos
                  </Link>
                )}
              </span>
            </p>
          )}
          {last?.status === "error" && (
            <p className="flex items-start gap-2 text-sm text-destructive">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              {last.error || "No se pudo leer el export."}
            </p>
          )}
          <Button
            variant="outline"
            className="min-h-11 md:min-h-9"
            onClick={() => input.current?.click()}
          >
            <FileArchive aria-hidden />
            {last?.status === "done" ? "Subir otro export" : "Subir export.zip"}
          </Button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Se importan los entrenos con su ruta y pulso, y la FC en reposo, la
        variabilidad (HRV), el sueño y los pasos de cada día. Lo que ya tengas
        de Garmin u otro reloj no se duplica ni se sobrescribe. Hasta 4 GB.
      </p>
    </Section>
  );
}

/** Cada día: automatización de Atajos que manda los entrenos recientes. */
function AppleShortcut({ data }: { data: Sources }) {
  return (
    <Section icon={Repeat} title="Cada día (Atajo del iPhone)">
      <p className="text-xs text-muted-foreground">
        Para que tus entrenos nuevos lleguen solos, crea una automatización en
        la app <strong>Atajos</strong> que los envíe una vez al día.
        {data.apple_last_at &&
          ` Último entreno recibido: ${formatDateTime(data.apple_last_at)}.`}
      </p>
      <ol className="list-decimal space-y-1.5 pl-5 text-xs text-muted-foreground">
        <li>
          Crea tu token personal aquí abajo y cópialo (es el mismo que usa
          Health Connect).
        </li>
        <li>
          En Atajos → <strong>Automatización</strong> → <strong>Nueva</strong> →{" "}
          <strong>Hora del día</strong> (por ejemplo, a las 23:00, cada día) →{" "}
          <strong>Ejecutar inmediatamente</strong>.
        </li>
        <li>
          Añade <strong>Buscar muestras de salud</strong>: tipo{" "}
          <em>Entrenamientos</em>, fecha de inicio en los últimos 2 días.
        </li>
        <li>
          Añade <strong>Repetir con cada</strong> elemento y, dentro, un{" "}
          <strong>Diccionario</strong> con <code>type</code> (Tipo),{" "}
          <code>start</code> (Fecha de inicio), <code>end</code> (Fecha de fin),{" "}
          <code>duration</code> (Duración), <code>distance</code> (Distancia) y{" "}
          <code>energy</code> (Energía).
        </li>
        <li>
          Opcional, para el pulso: otro{" "}
          <strong>Buscar muestras de salud</strong> de tipo{" "}
          <em>Frecuencia cardíaca</em> en los últimos 2 días.
        </li>
        <li>
          Añade <strong>Obtener contenido de URL</strong>: método POST, esta
          URL, cabecera <code>X-Api-Key</code> con tu token y cuerpo JSON con{" "}
          <code>workouts</code> = Resultados de la repetición (y{" "}
          <code>heart_rate</code> → <code>dates</code> / <code>values</code> con
          las fechas y valores del pulso).
        </li>
      </ol>
      <CopyRow
        value={data.apple_shortcut_url}
        label="Copiar la URL del Atajo"
      />
      <PersonalToken data={data} />
      <details className="text-xs text-muted-foreground">
        <summary className="min-h-11 cursor-pointer content-center font-medium text-foreground md:min-h-8">
          Formato que espera la app
        </summary>
        <pre className="mt-1 overflow-x-auto rounded bg-muted p-2">
          {`{
  "workouts": [{
    "type": "Correr",
    "start": "2026-10-01T09:00:00+02:00",
    "end": "2026-10-01T09:45:00+02:00",
    "duration": 2700,
    "distance": "8,2 km",
    "energy": 610
  }],
  "heart_rate": {
    "dates": ["2026-10-01T09:00:05+02:00", "…"],
    "values": [128, "…"]
  }
}`}
        </pre>
        <p className="mt-1">
          Acepta tipos en español o inglés, distancias con o sin unidad y
          duraciones en segundos o «45:10». Si las fechas no llegan bien, usa{" "}
          <strong>Formatear fecha</strong> con el formato ISO 8601.
        </p>
      </details>
      <p className="text-xs text-muted-foreground">
        Por el Atajo llegan el resumen y el pulso, pero no la ruta GPS: para el
        mapa, sube de vez en cuando el export de arriba. Reenviar los mismos
        días no duplica nada.
      </p>
    </Section>
  );
}

/** Apple Watch: historial con el export de Salud y entrenos nuevos con un Atajo diario. */
export function AppleWatch({ data }: { data: Sources }) {
  return (
    <div className="space-y-3">
      <AppleExport />
      <AppleShortcut data={data} />
    </div>
  );
}
