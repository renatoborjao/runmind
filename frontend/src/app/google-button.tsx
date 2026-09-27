"use client";

import { useEffect, useRef, useState } from "react";
import { getAuthConfig } from "@/lib/api";

// Botão "Continuar com Google" (Google Identity Services). Só aparece se o
// backend tem o Client ID configurado (GET /auth/config) — sem ele, a tela
// segue só com e-mail/senha. O Google devolve um ID token (`credential`) que
// o backend confere com o próprio Google.

type GsiCredential = { credential?: string };

type Gsi = {
  accounts: {
    id: {
      initialize: (o: { client_id: string; callback: (r: GsiCredential) => void; ux_mode?: string }) => void;
      renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
    };
  };
};

declare global {
  interface Window { google?: Gsi }
}

let scriptPromise: Promise<void> | null = null;

function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { scriptPromise = null; reject(new Error("gsi")); };
      document.head.appendChild(s);
    });
  }
  return scriptPromise;
}

export default function GoogleButton({
  onCredential,
  text = "continue_with",
}: {
  onCredential: (credential: string) => void;
  text?: "continue_with" | "signup_with" | "signin_with";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cb = useRef(onCredential);
  cb.current = onCredential;
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const { google_client_id } = await getAuthConfig();
      if (!google_client_id || !alive) return;
      try {
        await loadGsi();
      } catch {
        return; // sem Google (rede/bloqueio): fica só e-mail/senha
      }
      if (!alive || !ref.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: google_client_id,
        callback: (r) => { if (r.credential) cb.current(r.credential); },
      });
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text,
        locale: "pt-BR",
        width: Math.min(ref.current.offsetWidth || 320, 400),
      });
      setEnabled(true);
    })();
    return () => { alive = false; };
  }, [text]);

  return (
    <>
      <div ref={ref} className="gsi-slot" style={enabled ? undefined : { display: "none" }} />
      {enabled && <div className="auth-or"><span>ou</span></div>}
    </>
  );
}
