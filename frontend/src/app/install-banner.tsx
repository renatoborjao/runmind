"use client";

import { useEffect, useState } from "react";

// Banner que ensina a INSTALAR o app na tela do celular — e, principalmente,
// resolve a pegadinha do iPhone: "Adicionar à Tela de Início" só existe no
// SAFARI. Quem abre o link de dentro do Telegram/Instagram (webview) não acha a
// opção e trava. Aqui a gente detecta o contexto e mostra o passo certo.
//
// Regras:
//  - já instalado (standalone) -> não mostra nada.
//  - iOS no Safari -> passo do Compartilhar → Adicionar à Tela de Início.
//  - iOS fora do Safari (webview do Telegram, Chrome iOS...) -> "abra no Safari primeiro".
//  - Android com prompt nativo disponível -> botão "Instalar app" (1 toque).
//  - Android em webview (Telegram) -> "abra no Chrome".
//  - resto (desktop) -> nada.
// Dispensável (lembra no localStorage), best-effort — nunca quebra a tela.

type Mode =
  | "hidden"
  | "ios-safari"
  | "ios-open-safari"
  | "android-prompt"
  | "android-open-chrome";

const DISMISS_KEY = "rm_install_hint_dismissed_v1";

declare global {
  interface Window {
    __rmDeferredPrompt?: BeforeInstallPromptEvent | null;
  }
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function detect(): Mode {
  if (typeof window === "undefined" || typeof navigator === "undefined") return "hidden";

  const ua = navigator.userAgent || "";
  const nav = navigator as Navigator & { standalone?: boolean };

  const isStandalone =
    window.matchMedia?.("(display-mode: standalone)").matches || nav.standalone === true;
  if (isStandalone) return "hidden"; // já instalado

  const isIOS =
    /iP(hone|od|ad)/.test(ua) ||
    (nav.platform === "MacIntel" && (nav.maxTouchPoints ?? 0) > 1);
  const isAndroid = /Android/.test(ua);

  const isWebview = /Telegram|Instagram|FBAN|FBAV|FB_IAB|Line\/|; wv\)/i.test(ua);

  if (isIOS) {
    const isRealSafari =
      /Safari/.test(ua) && /Version\//.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua) && !isWebview;
    return isRealSafari ? "ios-safari" : "ios-open-safari";
  }

  if (isAndroid) {
    if (window.__rmDeferredPrompt) return "android-prompt";
    if (isWebview) return "android-open-chrome";
    return "hidden"; // Chrome sem prompt (talvez já instalável pelo menu) — não insiste
  }

  return "hidden";
}

export default function InstallBanner() {
  const [mode, setMode] = useState<Mode>("hidden");

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      /* localStorage bloqueado: segue mostrando */
    }

    setMode(detect());

    // o prompt nativo do Android pode chegar depois do mount
    const onPrompt = () => setMode(detect());
    window.addEventListener("rm-install-available", onPrompt);
    return () => window.removeEventListener("rm-install-available", onPrompt);
  }, []);

  if (mode === "hidden") return null;

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
    setMode("hidden");
  }

  async function androidInstall() {
    const dp = window.__rmDeferredPrompt;
    if (!dp) return;
    try {
      await dp.prompt();
      await dp.userChoice;
    } catch {
      /* ignore */
    }
    window.__rmDeferredPrompt = null;
    dismiss();
  }

  return (
    <section className="install-banner">
      <button className="ib-x" aria-label="Fechar" onClick={dismiss}>×</button>
      <div className="ib-ic">📲</div>
      <div className="ib-body">
        <strong>Instale o Ritmind no seu celular</strong>

        {mode === "ios-safari" && (
          <span>
            Toque em <b>Compartilhar</b> (o quadradinho com a seta ⬆️, na barra de baixo) e depois em{" "}
            <b>&quot;Adicionar à Tela de Início&quot;</b>. Assim as notificações também funcionam.
          </span>
        )}

        {mode === "ios-open-safari" && (
          <span>
            Você está no navegador do app (não é o Safari). Toque em <b>⋯</b> ou{" "}
            <b>Compartilhar</b> → <b>&quot;Abrir no Safari&quot;</b>. Já no Safari:{" "}
            <b>Compartilhar ⬆️</b> → <b>&quot;Adicionar à Tela de Início&quot;</b>. No iPhone só o Safari instala (e libera as notificações).
          </span>
        )}

        {mode === "android-prompt" && (
          <>
            <span>Um toque e o ícone vai pra sua tela inicial — com notificações no celular.</span>
            <button className="ib-btn" onClick={androidInstall}>Instalar app</button>
          </>
        )}

        {mode === "android-open-chrome" && (
          <span>
            Você está no navegador do app. Toque em <b>⋮</b> → <b>&quot;Abrir no Chrome&quot;</b>, e lá em{" "}
            <b>⋮</b> → <b>&quot;Instalar app&quot;</b>.
          </span>
        )}
      </div>
    </section>
  );
}
