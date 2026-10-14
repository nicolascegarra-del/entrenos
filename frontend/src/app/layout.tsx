import type { Metadata } from "next";

// Fuentes empaquetadas con la app (sin depender de Google Fonts en la build).
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource/nunito/600.css";
import "@fontsource/nunito/700.css";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "APP ENTRENOS",
  description: "Tus entrenamientos de Garmin: progresión, planificación y análisis plan vs real.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
