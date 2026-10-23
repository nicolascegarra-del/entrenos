"use client";

import { AccountCard } from "@/components/settings/account-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function CuentaPage() {
  return (
    <SettingsPage
      title="Cuenta y privacidad"
      subtitle="Contraseña, sesiones, exportar o borrar tus datos."
    >
      <AccountCard />
    </SettingsPage>
  );
}
