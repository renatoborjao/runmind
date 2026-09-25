"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import GoogleButton from "../google-button";
import PasswordField from "../password-field";
import { googleLogin, signup } from "@/lib/api";

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
  const [password, setPassword] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const [exists, setExists] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !invite.trim()) return;
    if (password.length < 8) { setErr("A senha precisa de pelo menos 8 caracteres."); return; }
    setSending(true);
    setErr("");
    setExists(false);
    const res = await signup(email.trim(), invite.trim(), password);
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

  // Google: o convite vai junto (conta nova); se o Google já tem conta, só entra
  async function onGoogle(credential: string) {
    if (!invite.trim()) {
      setErr("Coloca o código de convite primeiro, depois toca no Google.");
      return;
    }
    setSending(true);
    setErr("");
    const res = await googleLogin(credential, invite.trim());
    if (res.ok) { router.replace(res.created ? "/onboarding" : "/inicio"); return; }
    setErr(res.error || "Não consegui criar a conta com o Google.");
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
            O acesso é <b>por convite</b>. Coloca teu código e cria a conta
            com o Google ou com e-mail e senha — leva 1 minuto.
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
            <GoogleButton text="signup_with" onCredential={onGoogle} />

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

            <PasswordField
              id="password"
              label="Crie uma senha (mín. 8 caracteres)"
              value={password}
              onChange={(v) => { setPassword(v); if (err) setErr(""); }}
              autoComplete="new-password"
            />

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
          <p className="legal-foot muted">
            Ao criar a conta, você concorda com a{" "}
            <a className="link" href="/privacidade">Política de Privacidade</a>.
          </p>
        </div>
      </div>
    </main>
  );
}
