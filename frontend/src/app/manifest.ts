import type { MetadataRoute } from "next";

/** Manifiesto PWA: permite «Añadir a pantalla de inicio» y abrir la app sin barra del navegador. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "APP ENTRENOS",
    short_name: "Entrenos",
    description:
      "Tus entrenamientos de Garmin: progresión, planificación y análisis plan vs real.",
    lang: "es-ES",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#051937",
    theme_color: "#051937",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
