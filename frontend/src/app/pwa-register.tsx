"use client";

import { useEffect } from "react";

// Registra o service worker (casca offline + instalável como app). Silencioso:
// falha de registro nunca atrapalha o uso normal do app.
export default function PWARegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;

    // quando um service worker NOVO assume o controle, recarrega uma vez pra
    // pegar o visual/código novos na hora (sem o atleta precisar fechar o app).
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });

    const register = () => {
      // updateViaCache:"none" = o navegador SEMPRE revalida o sw.js pela rede
      // (não serve o SW do cache HTTP) — deixa a atualização do app confiável,
      // que é o gargalo recorrente no PWA (código novo não chegava no aparelho).
      navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then((reg) => {
        const check = () => reg.update().catch(() => {});
        check();
        // procura nova versão periodicamente e quando o app volta ao foco —
        // o PWA fica aberto na memória e não re-navega, então sem isso ele nunca
        // pegava um deploy novo. Se houver SW esperando, ativa na hora.
        setInterval(check, 60 * 1000);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") check();
        });
        reg.addEventListener("updatefound", () => {
          const w = reg.installing;
          if (!w) return;
          w.addEventListener("statechange", () => {
            if (w.state === "installed" && navigator.serviceWorker.controller) {
              w.postMessage("skip-waiting");
            }
          });
        });
      }).catch(() => {});
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
