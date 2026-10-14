import type { NextConfig } from "next";

// La web llama a la API en su mismo origen (/api/...) y Next la reenvía al backend:
// sin CORS y con la cookie de refresh SameSite=Strict funcionando en cualquier host.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` }];
  },
};

export default nextConfig;
