import { Settings } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";

export default function AjustesPage() {
  return (
    <ComingSoon
      title="Ajustes"
      icon={Settings}
      phase="Fase 3"
      description="Conexión con Garmin Connect, zonas de entrenamiento y umbrales (FC, ritmo, FTP)."
    />
  );
}
