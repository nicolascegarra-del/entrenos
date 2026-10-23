"use client";

import { NotificationsCard } from "@/components/settings/notifications-card";
import { SettingsPage } from "@/components/settings/settings-page";

export default function NotificacionesPage() {
  return (
    <SettingsPage title="Notificaciones">
      <NotificationsCard />
    </SettingsPage>
  );
}
