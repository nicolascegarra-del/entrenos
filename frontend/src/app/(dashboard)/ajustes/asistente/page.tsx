"use client";

import { AiProvidersCard } from "@/components/settings/ai-providers-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function AsistenteAjustesPage() {
  return (
    <SettingsPage
      title="Asistente IA"
      subtitle="Tu clave de ChatGPT, Gemini o Claude y el modelo que usa."
    >
      <AiProvidersCard />
    </SettingsPage>
  );
}
