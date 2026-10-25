import type { MetadataRoute } from "next";

/** Manifiesto PWA: permite «Añadir a pantalla de inicio» y abrir la app sin barra del navegador. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "KTrain",
    short_name: "KTrain",
    description:
      "Tu entrenador personal con IA para cualquier reloj: planes, métricas avanzadas y entrenos al reloj.",
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
