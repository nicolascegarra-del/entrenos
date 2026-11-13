"use client";

import { SettingsPage } from "@/components/settings/settings-page";
import { SocialPrivacyCard } from "@/components/settings/social-privacy-card";

export default function PrivacidadSocialPage() {
  return (
    <SettingsPage
      title="Privacidad social"
      subtitle="Quién te sigue y qué ven de tus entrenos"
    >
      <SocialPrivacyCard />
    </SettingsPage>
  );
}
