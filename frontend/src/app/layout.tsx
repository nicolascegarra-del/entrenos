import type { Metadata, Viewport } from "next";

// Fuentes empaquetadas con la app (sin depender de Google Fonts en la build).
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource/nunito/600.css";
import "@fontsource/nunito/700.css";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "APP ENTRENOS",
  description:
    "Tus entrenamientos de Garmin: progresión, planificación y análisis plan vs real.",
  applicationName: "APP ENTRENOS",
  // iOS: pantalla completa al abrirla desde la pantalla de inicio.
  appleWebApp: {
    capable: true,
    title: "Entrenos",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [{ url: "/favicon-32.png", sizes: "32x32", type: "image/png" }],
    apple: "/apple-touch-icon.png",
  },
};

// viewport-fit=cover: la barra inferior usa safe-area-inset para no quedar bajo la barra de gestos del móvil.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#051937",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
