"use client";

import { SettingsPage } from "@/components/settings/settings-page";
import { WatchConnections } from "@/components/settings/watch-connections";

export default function ConexionesPage() {
  return (
    <SettingsPage
      title="Conexiones"
      subtitle="Tu reloj: Garmin, Apple Watch, COROS, Android o ficheros."
    >
      <WatchConnections />
    </SettingsPage>
  );
}
