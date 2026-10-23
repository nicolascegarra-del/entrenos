"use client";

import { AiProvidersCard } from "@/components/settings/ai-providers-card";
import { CoachCard } from "@/components/settings/coach-card";
import { ReviewSettingsCard } from "@/components/settings/review-settings-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function AsistenteAjustesPage() {
  return (
    <SettingsPage
      title="Asistente IA"
      subtitle="Tu clave de IA, lo que tu entrenador sabe de ti y la revisión semanal."
    >
      <AiProvidersCard />
      <CoachCard />
      <ReviewSettingsCard />
    </SettingsPage>
  );
}
