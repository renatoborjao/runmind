import type { Metadata, Viewport } from "next";
import { Archivo, Manrope, IBM_Plex_Mono, Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import PWARegister from "./pwa-register";

const display = Archivo({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

// grotesca neutra e limpa (estilo Strava) — usada só no card de compartilhar,
// desenhado no canvas. Ver refreshCanvasFont em atividades/page.tsx.
const share = Inter({
  variable: "--font-share",
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
});

// wordmark "Ritmind" no card de compartilhar — display descolado/moderno.
const brand = Space_Grotesk({
  variable: "--font-brand",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const body = Manrope({
  variable: "--font-body",
  subsets: ["latin"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Ritmind",
  description: "Seu treinador de corrida com inteligência de verdade.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black",
    title: "Ritmind",
  },
  icons: {
    icon: "/icons/icon-192.png",
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#0C0D16",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className={`${display.variable} ${body.variable} ${mono.variable} ${share.variable} ${brand.variable}`}>
        {children}
        <PWARegister />
      </body>
    </html>
  );
}
