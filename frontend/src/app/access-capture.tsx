"use client";

import { useEffect, useState } from "react";
import { getMe, saveProfile, setPassword } from "@/lib/api";

// Cartão "Garanta teu acesso" (Início): quem ainda não tem SENHA — hoje, todo
// atleta que entrou pelo código do coach no Telegram — cria aqui, enquanto está
// logado. Pede o e-mail junto se o perfil não tem (o login é e-mail + senha).
// Some quando o acesso está garantido. Dispensar só adia (3 dias): é o que
// evita o atleta ficar trancado pra fora ao trocar de celular. Best-effort —
// nunca quebra a home.

const SNOOZE_KEY = "rm_access_capture_snooze_until";

const SNOOZE_MS = 3 * 24 * 3600 * 1000;

type State = "hidden" | "ask" | "saving" | "done";

export default function AccessCapture() {
  const [state, setState] = useState<State>("hidden");
  const [needsEmail, setNeedsEmail] = useState(false);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    try {
      if (Number(localStorage.getItem(SNOOZE_KEY) || 0) > Date.now()) return;
    } catch { /* segue */ }
    let alive = true;
    getMe().then((me) => {
      if (!alive || !me || me.has_password) return;
      setNeedsEmail(!(me.email && me.email.trim()));
      setState("ask");
    });
    return () => { alive = false; };
  }, []);

  function snooze() {
    try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_MS)); } catch { /* ignore */ }
    setState("hidden");
  }

  async function save() {
    setErr("");
    const e = email.trim();
    if (needsEmail && (!e.includes("@") || !e.includes("."))) { setErr("Digite um e-mail válido."); return; }
    if (pw.length < 8) { setErr("A senha precisa de pelo menos 8 caracteres."); return; }
    setState("saving");
    if (needsEmail) {
      const r = await saveProfile({ email: e });
      if (!r.ok) { setErr(r.message || "Não consegui salvar o e-mail."); setState("ask"); return; }
      setNeedsEmail(false);
    }
    const r = await setPassword(pw);
    if (!r.ok) { setErr(r.error || "Não consegui salvar a senha."); setState("ask"); return; }
    setState("done");
    setTimeout(() => setState("hidden"), 3500);
  }

  if (state === "hidden") return null;

  if (state === "done") {
    return (
      <section className="card email-capture">
        <div className="ec-ic">✅</div>
        <div className="ec-body">
          <strong>Acesso garantido!</strong>
          <span>Agora é só entrar com teu e-mail e senha — em qualquer celular, sem depender do Telegram.</span>
        </div>
      </section>
    );
  }

  return (
    <section className="card email-capture">
      <button className="ib-x" aria-label="Depois" onClick={snooze}>×</button>
      <div className="ec-ic">🔐</div>
      <div className="ec-body">
        <strong>Garanta teu acesso</strong>
        <span>
          Cria uma senha pra entrar no app direto — se trocar de celular ou a sessão
          acabar, você não fica de fora.
        </span>
        {needsEmail && (
          <div className="ec-row">
            <input
              type="email" inputMode="email" autoComplete="email" placeholder="Teu e-mail"
              value={email} onChange={(ev) => { setEmail(ev.target.value); setErr(""); }}
            />
          </div>
        )}
        <div className="ec-row">
          <input
            type={show ? "text" : "password"} autoComplete="new-password"
            placeholder="Senha (mín. 8 caracteres)"
            value={pw} onChange={(ev) => { setPw(ev.target.value); setErr(""); }}
          />
          <button type="button" className="ec-show" onClick={() => setShow((s) => !s)}>
            {show ? "ocultar" : "mostrar"}
          </button>
        </div>
        <button className="ib-btn" onClick={save} disabled={state === "saving"}>
          {state === "saving" ? "Salvando…" : "Criar senha"}
        </button>
        {err && <span className="ec-err">{err}</span>}
      </div>
    </section>
  );
}
