"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import GoogleButton from "../google-button";
import PasswordField from "../password-field";
import {
  getMe,
  googleLogin,
  loginWithPassword,
  requestLogin,
  resetPassword,
  saveProfile,
  verifyToken,
} from "@/lib/api";

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

// depois de entrar: cadastro incompleto vai pro wizard, senão pro início
async function goAfterLogin(router: ReturnType<typeof useRouter>) {
  const me = await getMe();
  router.replace(me && !me.onboarding_complete ? "/onboarding" : "/inicio");
}

type Mode = "login" | "forgot" | "code";

// Tela depois de entrar por link/código: cria (ou redefine) a senha — é ela
// que garante que o atleta volta sozinho, sem depender do Telegram/e-mail.
function SetPasswordCard({ resetToken, reset }: { resetToken: string; reset: boolean }) {
  const router = useRouter();
  const [pw, setPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  // atleta do Telegram sem e-mail: o login é e-mail + senha, então pede aqui
  const [needsEmail, setNeedsEmail] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => { (async () => { const me = await getMe(); setNeedsEmail(!!me && !me.email); })(); }, []);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr("");
    if (needsEmail) {
      const saved = await saveProfile({ email: email.trim() });
      if (!saved.ok) { setErr(saved.message || "Não consegui salvar o e-mail."); setSaving(false); return; }
    }
    const res = await resetPassword(resetToken, pw);
    if (res.ok) { await goAfterLogin(router); return; }
    setErr(res.error || "Não consegui salvar a senha.");
    setSaving(false);
  }

  return (
    <div className="card">
      <h1 className="auth-title">{reset ? "Crie uma senha nova" : "Entrou! ✅"}</h1>
      <p className="auth-sub">
        {reset
          ? "Escolhe a senha nova pra entrar no Ritmind."
          : "Cria uma senha pra entrar direto da próxima vez — sem precisar pedir código."}
      </p>
      <form onSubmit={onSave}>
        {needsEmail && (
          <div className="field">
            <label htmlFor="setemail">Teu e-mail (é com ele que você entra)</label>
            <input
              id="setemail" type="email" inputMode="email" autoComplete="email"
              placeholder="voce@exemplo.com" value={email}
              onChange={(e) => setEmail(e.target.value)} required
            />
          </div>
        )}
        <PasswordField id="newpw" label="Senha (mín. 8 caracteres)" value={pw} onChange={setPw} autoComplete="new-password" />
        {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
        <button className="btn" type="submit" disabled={saving || pw.length < 8 || (needsEmail && !email.includes("@"))}>
          {saving ? "Salvando…" : "Salvar senha"}
        </button>
      </form>
      {!reset && (
        <p className="muted center" style={{ marginTop: 14 }}>
          <a className="link" onClick={() => goAfterLogin(router)}>Agora não</a>
        </p>
      )}
    </div>
  );
}

function EntrarInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");
  const wantsReset = params.get("reset") === "1";

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [forgotSent, setForgotSent] = useState(false);
  const [code, setCode] = useState("");

  // Google sem conta: pede o convite e reenvia a mesma credencial
  const [googleCred, setGoogleCred] = useState<string | null>(null);
  const [invite, setInvite] = useState("");

  // entrou por link/código: oferece criar/redefinir a senha
  const [afterToken, setAfterToken] = useState<{ resetToken: string; reset: boolean } | null>(null);
  const [tokenStatus, setTokenStatus] = useState<"verifying" | "error">("verifying");

  async function handleVerified(res: { resetToken: string; hasPassword: boolean }, reset: boolean) {
    if (reset || !res.hasPassword) {
      setAfterToken({ resetToken: res.resetToken, reset: reset && res.hasPassword });
      return;
    }
    await goAfterLogin(router);
  }

  // Veio de um link (?token=): troca por sessão.
  useEffect(() => {
    if (!token) return;
    (async () => {
      const res = await verifyToken(token);
      if (res) await handleVerified(res, wantsReset);
      else setTokenStatus("error");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    const res = await loginWithPassword(email.trim(), password);
    if (res.ok) { await goAfterLogin(router); return; }
    setErr(res.error || "Não consegui entrar.");
    setBusy(false);
  }

  async function onGoogle(credential: string, inviteCode?: string) {
    setBusy(true);
    setErr("");
    const res = await googleLogin(credential, inviteCode);
    if (res.ok) { await goAfterLogin(router); return; }
    if (res.needsInvite) { setGoogleCred(credential); setBusy(false); return; }
    setErr(res.error || "Não consegui entrar com o Google.");
    setBusy(false);
  }

  async function onForgot(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await requestLogin(email.trim());
    setBusy(false);
    setForgotSent(true);
  }

  async function onCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    const res = await verifyToken(code.trim());
    if (res) { await handleVerified(res, false); return; }
    setErr("Código inválido ou expirado. Peça um novo ao coach.");
    setBusy(false);
  }

  if (afterToken) return <SetPasswordCard resetToken={afterToken.resetToken} reset={afterToken.reset} />;

  if (token) {
    return (
      <div className="card center">
        {tokenStatus === "verifying" ? (
          <p className="auth-sub" style={{ margin: 0 }}>Entrando…</p>
        ) : (
          <>
            <p className="notice err">Esse link expirou ou já foi usado.</p>
            <p style={{ marginTop: 16 }}>
              <a className="link" onClick={() => router.replace("/entrar")}>Voltar pro login</a>
            </p>
          </>
        )}
      </div>
    );
  }

  // Google válido, mas conta nova: convite
  if (googleCred) {
    return (
      <div className="card">
        <h1 className="auth-title">Quase lá!</h1>
        <p className="auth-sub">
          Ainda não tem conta com esse Google. O acesso é <b>por convite</b> — coloca teu código pra criar.
        </p>
        <form onSubmit={(e) => { e.preventDefault(); onGoogle(googleCred, invite.trim()); }}>
          <div className="field">
            <label htmlFor="invite">Código de convite</label>
            <input
              id="invite" type="text" autoCapitalize="characters" placeholder="Ex.: RIT-7K2M"
              value={invite} onChange={(e) => setInvite(e.target.value)} required
              style={{ textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono), monospace" }}
            />
          </div>
          {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
          <button className="btn" type="submit" disabled={busy || !invite.trim()}>
            {busy ? "Criando…" : "Criar conta"}
          </button>
        </form>
        <p className="muted center" style={{ marginTop: 14 }}>
          <a className="link" onClick={() => { setGoogleCred(null); setErr(""); }}>Voltar</a>
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h1 className="auth-title">Entrar no Ritmind</h1>

      {mode === "login" && (
        <>
          <GoogleButton onCredential={(c) => onGoogle(c)} />

          <form onSubmit={onLogin}>
            <div className="field">
              <label htmlFor="email">E-mail</label>
              <input
                id="email" type="email" inputMode="email" autoComplete="email"
                placeholder="voce@exemplo.com" value={email}
                onChange={(e) => { setEmail(e.target.value); setErr(""); }} required
              />
            </div>
            <PasswordField id="password" label="Senha" value={password} onChange={(v) => { setPassword(v); setErr(""); }} autoComplete="current-password" />
            {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "Entrando…" : "Entrar"}
            </button>
          </form>

          <p className="muted center" style={{ marginTop: 14, display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}>
            <a className="link" onClick={() => { setMode("forgot"); setErr(""); }}>Esqueci a senha</a>
            <a className="link" onClick={() => { setMode("code"); setErr(""); }}>Tenho um código</a>
          </p>
        </>
      )}

      {mode === "forgot" && (
        forgotSent ? (
          <>
            <div className="notice ok">
              Se esse e-mail tiver conta, mandamos um link pra criar uma senha nova. Confere a caixa de entrada (e o spam). 📬
            </div>
            <p className="auth-hint">
              Também é atleta pelo Telegram? Mande <b>&quot;quero o app&quot;</b> ao coach que ele te manda um acesso na hora.
            </p>
            <p className="muted center" style={{ marginTop: 10 }}>
              <a className="link" onClick={() => { setMode("login"); setForgotSent(false); }}>Voltar pro login</a>
            </p>
          </>
        ) : (
          <form onSubmit={onForgot}>
            <p className="auth-sub">Coloca teu e-mail que a gente te manda um link pra criar uma senha nova.</p>
            <div className="field">
              <label htmlFor="femail">E-mail</label>
              <input
                id="femail" type="email" inputMode="email" autoComplete="email"
                placeholder="voce@exemplo.com" value={email}
                onChange={(e) => setEmail(e.target.value)} required
              />
            </div>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Enviando…" : "Enviar link"}</button>
            <p className="muted center" style={{ marginTop: 14 }}>
              <a className="link" onClick={() => setMode("login")}>Voltar</a>
            </p>
          </form>
        )
      )}

      {mode === "code" && (
        <form onSubmit={onCode}>
          <p className="auth-sub">Recebeu um código do coach no Telegram? Digita aqui.</p>
          <div className="field">
            <label htmlFor="code">Código de acesso</label>
            <input
              id="code" type="text" autoCapitalize="characters" autoComplete="one-time-code"
              placeholder="Ex.: ABC-DEF" value={code}
              onChange={(e) => { setCode(e.target.value); setErr(""); }} required
              style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace" }}
            />
          </div>
          {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
          <button className="btn" type="submit" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
          <p className="muted center" style={{ marginTop: 14 }}>
            <a className="link" onClick={() => { setMode("login"); setErr(""); }}>Voltar</a>
          </p>
        </form>
      )}

      <p className="auth-hint">
        Primeira vez no Ritmind?{" "}
        <a className="link" onClick={() => router.push("/cadastro")}>Criar conta</a>
      </p>

      <p className="auth-hint" style={{ marginTop: 4 }}>
        Já é atleta pelo Telegram? Mande <b>&quot;quero o app&quot;</b> ao{" "}
        <a className="link" href={TELEGRAM_COACH} target="_blank" rel="noopener noreferrer">coach</a>. 📲
      </p>
      <p className="legal-foot muted">
        <a className="link" href="/privacidade">Política de Privacidade</a>
      </p>
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
