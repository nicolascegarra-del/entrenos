"use client";

import { SettingsPage } from "@/components/settings/settings-page";
import { WatchConnections } from "@/components/settings/watch-connections";

export default function ConexionesPage() {
  return (
    <SettingsPage
      title="Conexiones"
      subtitle="Tu reloj o anillo: Garmin, Apple Watch, COROS, Suunto, Amazfit, Xiaomi, Android, Oura o ficheros."
    >
      <WatchConnections />
    </SettingsPage>
  );
}
