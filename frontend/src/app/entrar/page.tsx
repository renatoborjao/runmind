"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { requestLogin, verifyToken } from "@/lib/api";

const TELEGRAM_COACH = "https://t.me/runmind_coach_bot";

function Wordmark() {
  return (
    <div className="brand">
      <span className="mark" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 12h4l2.5-7 4 15 2.5-8H22" />
        </svg>
      </span>
      <span className="word">Rit<b>mind</b></span>
    </div>
  );
}

type Status = "form" | "sending" | "sent" | "verifying" | "error";

function EntrarInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");

  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>(token ? "verifying" : "form");
  const [showEmail, setShowEmail] = useState(false);

  // Veio de um magic link (?token=): troca por sessão e entra.
  useEffect(() => {
    if (!token) return;
    (async () => {
      const ok = await verifyToken(token);
      if (ok) {
        router.replace("/inicio");
      } else {
        setStatus("error");
      }
    })();
  }, [token, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    await requestLogin(email.trim());
    setStatus("sent");
  }

  if (token) {
    return (
      <div className="card center">
        {status === "verifying" ? (
          <p className="auth-sub" style={{ margin: 0 }}>Entrando…</p>
        ) : (
          <>
            <p className="notice err">Esse link expirou ou já foi usado.</p>
            <p style={{ marginTop: 16 }}>
              <a className="link" onClick={() => router.replace("/entrar")}>
                Pedir um novo link
              </a>
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <h1 className="auth-title">Entrar no Ritmind</h1>
      <p className="auth-sub">
        Seu acesso é <b>sem senha</b>. Peça o link ao coach no Telegram — chega na
        hora, no chat.
      </p>

      <a className="btn btn-tg" href={TELEGRAM_COACH} target="_blank" rel="noopener noreferrer">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden>
          <path d="M9.8 15.6l-.4 4c.5 0 .7-.2 1-.5l2.4-2.3 5 3.6c.9.5 1.6.2 1.8-.8l3.3-15.3c.3-1.3-.5-1.8-1.4-1.5L1.2 9.4C-.1 9.9 0 10.6 1 10.9l5.2 1.6L18.3 5c.6-.4 1.1-.2.7.2z" />
        </svg>
        Receber link no Telegram
      </a>
      <p className="auth-hint">
        No coach, é só mandar <b>&quot;quero o app&quot;</b> que eu te envio o link. 📲
      </p>

      <div className="auth-or"><span>ou</span></div>

      {showEmail ? (
        status === "sent" ? (
          <>
            <div className="notice ok">
              Se este e-mail estiver cadastrado, o link de acesso já está a caminho.
              Confira sua caixa de entrada. 📬
            </div>
            <p className="muted center" style={{ marginTop: 16 }}>
              Não chegou?{" "}
              <a className="link" onClick={() => setStatus("form")}>
                Tentar de novo
              </a>
            </p>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="email">Seu e-mail</label>
              <input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="voce@exemplo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <button className="btn" type="submit" disabled={status === "sending"}>
              {status === "sending" ? "Enviando…" : "Enviar link por e-mail"}
            </button>
          </form>
        )
      ) : (
        <p className="muted center" style={{ margin: 0 }}>
          <a className="link" onClick={() => setShowEmail(true)}>
            Entrar por e-mail
          </a>
        </p>
      )}
    </div>
  );
}

export default function EntrarPage() {
  return (
    <main className="stage">
      <div className="phone" style={{ justifyContent: "center", flex: 1, maxWidth: 400 }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
          <Wordmark />
        </div>
        <Suspense fallback={<div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>}>
          <EntrarInner />
        </Suspense>
      </div>
    </main>
  );
}
