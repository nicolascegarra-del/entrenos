"use client";

import { SocialGate } from "@/components/social/social-setup";

/** Todas las pantallas de Amigos piden antes el alta (nombre visible y @) si aún no la tienes. */
export default function SocialLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SocialGate>{children}</SocialGate>;
}
