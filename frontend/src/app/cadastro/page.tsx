"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signup, verifyToken } from "@/lib/api";

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

type Step = "form" | "sending" | "sent";

export default function CadastroPage() {
  const router = useRouter();

  const [step, setStep] = useState<Step>("form");
  const [email, setEmail] = useState("");
  const [invite, setInvite] = useState("");
  const [formErr, setFormErr] = useState("");

  const [code, setCode] = useState("");
  const [codeStatus, setCodeStatus] = useState<"idle" | "verifying" | "error">("idle");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !invite.trim()) return;
    setStep("sending");
    setFormErr("");
    const res = await signup(email.trim(), invite.trim());
    if (res.ok) {
      setStep("sent");
    } else {
      setFormErr(res.error || "Não consegui te cadastrar.");
      setStep("form");
    }
  }

  async function onCode(e: React.FormEvent) {
    e.preventDefault();
    const c = code.trim();
    if (!c) return;
    setCodeStatus("verifying");
    const ok = await verifyToken(c);
    if (ok) {
      // conta criada e logada: vai pro wizard de onboarding
      router.replace("/onboarding");
    } else {
      setCodeStatus("error");
    }
  }

  return (
    <main className="stage">
      <div className="phone" style={{ justifyContent: "center", flex: 1, maxWidth: 400 }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
          <Wordmark />
        </div>

        {step === "sent" ? (
          <div className="card">
            <h1 className="auth-title">Confere seu e-mail 📬</h1>
            <p className="auth-sub">
              Enviamos um <b>código de acesso</b> pra <b>{email}</b>. Digite ele
              aqui pra criar sua conta.
            </p>

            <form onSubmit={onCode}>
              <div className="field">
                <label htmlFor="code">Código de acesso</label>
                <input
                  id="code"
                  type="text"
                  inputMode="text"
                  autoCapitalize="characters"
                  autoComplete="one-time-code"
                  placeholder="Ex.: ABC-DEF"
                  value={code}
                  onChange={(e) => {
                    setCode(e.target.value);
                    if (codeStatus === "error") setCodeStatus("idle");
                  }}
                  style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace" }}
                  required
                />
              </div>
              {codeStatus === "error" && (
                <p className="notice err" style={{ marginTop: 0 }}>
                  Código inválido ou expirado. Confere no e-mail (vale por 1h).
                </p>
              )}
              <button className="btn" type="submit" disabled={codeStatus === "verifying"}>
                {codeStatus === "verifying" ? "Entrando…" : "Criar conta e continuar"}
              </button>
            </form>

            <p className="muted center" style={{ marginTop: 16 }}>
              Não chegou?{" "}
              <a className="link" onClick={() => { setStep("form"); setCode(""); setCodeStatus("idle"); }}>
                Voltar
              </a>
            </p>
          </div>
        ) : (
          <div className="card">
            <h1 className="auth-title">Criar conta no Ritmind</h1>
            <p className="auth-sub">
              O acesso é <b>por convite</b>. Coloca seu código, seu e-mail, e a
              gente te manda um acesso <b>sem senha</b>.
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
                  onChange={(e) => { setInvite(e.target.value); if (formErr) setFormErr(""); }}
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
                  onChange={(e) => { setEmail(e.target.value); if (formErr) setFormErr(""); }}
                  required
                />
              </div>
              {formErr && (
                <p className="notice err" style={{ marginTop: 0 }}>{formErr}</p>
              )}
              <button className="btn" type="submit" disabled={step === "sending"}>
                {step === "sending" ? "Enviando…" : "Criar conta"}
              </button>
            </form>

            <p className="auth-hint">
              Já tem conta?{" "}
              <a className="link" onClick={() => router.replace("/entrar")}>
                Entrar
              </a>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
