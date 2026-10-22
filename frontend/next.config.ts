import type { NextConfig } from "next";

// La web llama a la API en su mismo origen (/api/...) y Next la reenvía al backend:
// sin CORS y con la cookie de refresh SameSite=Strict funcionando en cualquier host.
const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
const isProduction = process.env.NODE_ENV === "production";

/**
 * Política de contenido: solo recursos propios, más las teselas del mapa (OpenStreetMap) y el
 * captcha del registro (Cloudflare Turnstile: script + iframe de challenges.cloudflare.com).
 * Next inserta scripts y estilos en línea para la hidratación, de ahí 'unsafe-inline';
 * en desarrollo además necesita 'unsafe-eval' (recarga en caliente).
 */
const TURNSTILE = "https://challenges.cloudflare.com";
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isProduction ? "" : " 'unsafe-eval'"} ${TURNSTILE}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
  "font-src 'self' data:",
  `connect-src 'self' ${TURNSTILE}`,
  `frame-src ${TURNSTILE}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
  // Los navegadores ignoran HSTS si la página no llega por HTTPS (p. ej. en local).
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
