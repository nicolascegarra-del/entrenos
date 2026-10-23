"use client";

import { GarminCard } from "@/components/settings/garmin-card";
import { OtherWatchesCard } from "@/components/settings/other-watches-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function ConexionesPage() {
  return (
    <SettingsPage
      title="Conexiones"
      subtitle="Garmin, otros relojes e importar ficheros."
    >
      <GarminCard />
      <OtherWatchesCard />
    </SettingsPage>
  );
}
