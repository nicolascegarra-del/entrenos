"use client";

import { AccountCard } from "@/components/settings/account-card";
import { AiProvidersCard } from "@/components/settings/ai-providers-card";
import { GarminCard } from "@/components/settings/garmin-card";
import { NotificationsCard } from "@/components/settings/notifications-card";
import { OtherWatchesCard } from "@/components/settings/other-watches-card";
import { ProfileCard } from "@/components/settings/profile-card";

export default function AjustesPage() {
  return (
    <section className="space-y-4">
      <h1 className="font-heading text-2xl font-bold md:text-3xl">Ajustes</h1>
      <div className="grid max-w-5xl grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
        <GarminCard />
        <ProfileCard />
        <div className="lg:col-span-2">
          <OtherWatchesCard />
        </div>
        <div className="lg:col-span-2">
          <NotificationsCard />
        </div>
        <div className="lg:col-span-2">
          <AiProvidersCard />
        </div>
        <div className="lg:col-span-2">
          <AccountCard />
        </div>
      </div>
    </section>
  );
}
