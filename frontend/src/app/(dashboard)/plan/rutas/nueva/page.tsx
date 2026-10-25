"use client";

import { PageHeader } from "@/components/layout/page-header";
import { RouteEditor } from "@/components/routes/route-editor";

/** Crear una ruta en el mapa. */
export default function NuevaRutaPage() {
  return (
    <section className="space-y-3">
      <PageHeader
        title="Nueva ruta"
        back={{ href: "/plan/rutas", label: "Rutas" }}
      />
      <RouteEditor />
    </section>
  );
}
