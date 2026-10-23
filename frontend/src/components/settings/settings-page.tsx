import { PageHeader } from "@/components/layout/page-header";

/** Subpágina de Ajustes: volver a la lista y el contenido de esa sección. */
export function SettingsPage({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader
        back={{ href: "/ajustes", label: "Ajustes" }}
        title={title}
        subtitle={subtitle}
      />
      <div className="space-y-4 md:space-y-6">{children}</div>
    </section>
  );
}
