"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signup } from "@/lib/api";

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

export default function CadastroPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [invite, setInvite] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const [exists, setExists] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !invite.trim()) return;
    setSending(true);
    setErr("");
    setExists(false);
    const res = await signup(email.trim(), invite.trim());
    if (res.ok && res.loggedIn) {
      // conta criada e logada: segue direto pro wizard de onboarding
      router.replace("/onboarding");
      return;
    }
    if (res.ok && !res.loggedIn) {
      // e-mail já tem conta: manda entrar
      setExists(true);
      setSending(false);
      return;
    }
    setErr(res.error || "Não consegui te cadastrar.");
    setSending(false);
  }

  return (
    <main className="stage">
      <div className="phone" style={{ justifyContent: "center", flex: 1, maxWidth: 400 }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
          <Wordmark />
        </div>

        <div className="card">
          <h1 className="auth-title">Criar conta no Ritmind</h1>
          <p className="auth-sub">
            O acesso é <b>por convite</b>. Coloca seu código e seu e-mail pra
            começar — leva 1 minuto.
          </p>

          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="invite">Código de convite</label>
              <input
                id="invite"
                type="text"
                autoCapitalize="characters"
                placeholder="Ex.: RIT-7K2M"
                value={invite}
                onChange={(e) => { setInvite(e.target.value); if (err) setErr(""); if (exists) setExists(false); }}
                style={{ textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono), monospace" }}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="email">Seu e-mail</label>
              <input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="voce@exemplo.com"
                value={email}
                onChange={(e) => { setEmail(e.target.value); if (err) setErr(""); if (exists) setExists(false); }}
                required
              />
            </div>

            {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
            {exists && (
              <div className="notice" style={{ marginTop: 0 }}>
                Esse e-mail já tem conta.{" "}
                <a className="link" onClick={() => router.replace("/entrar")}>Entrar</a>
              </div>
            )}

            <button className="btn" type="submit" disabled={sending}>
              {sending ? "Criando…" : "Criar conta e começar"}
            </button>
          </form>

          <p className="auth-hint">
            Já tem conta?{" "}
            <a className="link" onClick={() => router.replace("/entrar")}>
              Entrar
            </a>
          </p>
        </div>
      </div>
    </main>
  );
}
