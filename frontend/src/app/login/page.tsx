import type { Metadata } from "next";

import { Landing } from "@/components/landing/landing";

export const metadata: Metadata = {
  title: "KTrain · Tu entrenador personal con IA para cualquier reloj",
  description:
    "Entrenos de Garmin, COROS, Apple Watch o Android en un sitio, métricas avanzadas, planes que se envían al reloj y un entrenador con IA que usa tu propia cuenta.",
};

/** Página pública: landing de KTrain con el inicio de sesión. */
export default function LoginPage() {
  return <Landing />;
}
