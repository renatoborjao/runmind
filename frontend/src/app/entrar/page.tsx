"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { requestLogin, verifyToken } from "@/lib/api";

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
        Digite seu e-mail que a gente manda um link de acesso — sem senha.
      </p>

      {status === "sent" ? (
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
            {status === "sending" ? "Enviando…" : "Enviar link de acesso"}
          </button>
        </form>
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
