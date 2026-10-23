"use client";

import { ProfileCard } from "@/components/settings/profile-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function PerfilPage() {
  return (
    <SettingsPage
      title="Perfil"
      subtitle="Edad, sexo, peso y altura: afinan zonas, VO2max y marcas por edad."
    >
      <ProfileCard />
    </SettingsPage>
  );
}
