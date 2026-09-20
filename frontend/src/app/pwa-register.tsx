"use client";

import { useEffect } from "react";

// Registra o service worker (casca offline + instalável como app). Silencioso:
// falha de registro nunca atrapalha o uso normal do app.
export default function PWARegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    // RECUPERAÇÃO DE CHUNK VELHO (tela branca pós-deploy): o deploy troca os
    // arquivos hasheados do Next e remove os antigos; um app JÁ ABERTO (PWA na
    // memória) pode tentar carregar um chunk que não existe mais -> "erro ao
    // buscar o script" / tela branca. Aqui a gente recarrega UMA vez: a
    // navegação é network-first, então volta o HTML novo com os chunks atuais.
    // sessionStorage evita loop; some ao carregar com sucesso (5s de pé).
    const CHUNK_RE = /ChunkLoadError|Loading chunk|Importing a module script failed|error loading dynamically imported module|Failed to fetch dynamically imported module|fetching the script/i;
    const reloadOnce = () => {
      try {
        if (sessionStorage.getItem("rm_chunk_reload")) return;
        sessionStorage.setItem("rm_chunk_reload", "1");
      } catch { /* sem storage: recarrega mesmo assim (1ª vez) */ }
      window.location.reload();
    };
    const onErr = (e: ErrorEvent) => {
      const t = e.target as (HTMLElement & { src?: string; href?: string }) | null;
      // erro de carregamento de <script>/<link> (chunk) não tem mensagem e não
      // borbulha — pega na fase de captura pelo alvo. SÓ os NOSSOS chunks do Next
      // (mesma origem, /_next/) disparam reload — um CDN que oscila (Leaflet,
      // tiles) tem fallback próprio e NÃO deve recarregar o app.
      if (t && (t.tagName === "SCRIPT" || t.tagName === "LINK")) {
        const url = t.src || t.href || "";
        if (url.startsWith(window.location.origin) && url.includes("/_next/")) reloadOnce();
        return;
      }
      if (CHUNK_RE.test(e.message || e.error?.message || "")) reloadOnce();
    };
    const onRej = (e: PromiseRejectionEvent) => {
      const r = e.reason;
      if (CHUNK_RE.test(`${r?.name ?? ""} ${r?.message ?? r ?? ""}`)) reloadOnce();
    };
    window.addEventListener("error", onErr, true); // capture: pega erro de recurso
    window.addEventListener("unhandledrejection", onRej);
    // carregou de boa? libera o guarda pra um PRÓXIMO deploy poder recuperar.
    const clearGuard = setTimeout(() => {
      try { sessionStorage.removeItem("rm_chunk_reload"); } catch { /* ok */ }
    }, 5000);

    if (!("serviceWorker" in navigator)) {
      return () => {
        window.removeEventListener("error", onErr, true);
        window.removeEventListener("unhandledrejection", onRej);
        clearTimeout(clearGuard);
      };
    }

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

    const cleanup = () => {
      window.removeEventListener("error", onErr, true);
      window.removeEventListener("unhandledrejection", onRej);
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("load", register);
      clearTimeout(clearGuard);
    };

    // a página estática carrega rápido: o evento 'load' pode já ter disparado
    // antes deste efeito rodar — nesse caso registra na hora.
    if (document.readyState === "complete") {
      register();
      return cleanup;
    }

    window.addEventListener("load", register);
    return cleanup;
  }, []);

  return null;
}
