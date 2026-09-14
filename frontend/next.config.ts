import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Export estático: o Caddy serve os arquivos direto (sem Node na VM) e faz
  // proxy de /api/* pro backend FastAPI (mesma origem → cookie de sessão sem
  // dor de cross-site).
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
