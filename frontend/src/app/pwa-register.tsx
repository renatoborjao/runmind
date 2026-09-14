"use client";

import { useEffect } from "react";

// Registra o service worker (casca offline + instalável como app). Silencioso:
// falha de registro nunca atrapalha o uso normal do app.
export default function PWARegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    };

    // guarda o prompt nativo de instalar (Android/Chrome) pra o InstallBanner
    // oferecer o botão "Instalar app" (1 toque). iOS não emite este evento.
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      (window as unknown as { __rmDeferredPrompt?: Event }).__rmDeferredPrompt = e;
      window.dispatchEvent(new Event("rm-install-available"));
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // a página estática carrega rápido: o evento 'load' pode já ter disparado
    // antes deste efeito rodar — nesse caso registra na hora.
    if (document.readyState === "complete") {
      register();
      return;
    }

    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
