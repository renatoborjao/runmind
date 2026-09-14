"use client";

import { useEffect, useState } from "react";
import { getProfile, saveProfile } from "@/lib/api";

// Card que pede o e-mail no app pra quem entrou pelo Telegram e ainda não tem
// e-mail no perfil. Semeia o login por e-mail atleta-a-atleta (self-service) +
// vira canal de recuperação de acesso. Some quando já tem e-mail, quando salva,
// ou quando o atleta dispensa. Best-effort — nunca quebra a home.

const DISMISS_KEY = "rm_email_capture_dismissed_v1";

type State = "hidden" | "ask" | "saving" | "done" | "error";

export default function EmailCapture() {
  const [state, setState] = useState<State>("hidden");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      /* segue */
    }
    let alive = true;
    getProfile().then((p) => {
      if (alive && p && !(p.email && p.email.trim())) setState("ask");
    });
    return () => {
      alive = false;
    };
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
    setState("hidden");
  }

  async function save() {
    const e = email.trim();
    if (!e || !e.includes("@") || !e.includes(".")) {
      setMsg("Digite um e-mail válido.");
      setState("error");
      return;
    }
    setState("saving");
    const r = await saveProfile({ email: e });
    if (r.ok) {
      setState("done");
      // some sozinho depois de um instante e não pergunta de novo
      try {
        localStorage.setItem(DISMISS_KEY, "1");
      } catch {
        /* ignore */
      }
      setTimeout(() => setState("hidden"), 2600);
    } else {
      setMsg(r.message || "Não consegui salvar.");
      setState("error");
    }
  }

  if (state === "hidden") return null;

  if (state === "done") {
    return (
      <section className="card email-capture">
        <div className="ec-ic">✅</div>
        <div className="ec-body">
          <strong>E-mail salvo!</strong>
          <span>Agora você também pode entrar por e-mail e recuperar o acesso se trocar de celular.</span>
        </div>
      </section>
    );
  }

  return (
    <section className="card email-capture">
      <button className="ib-x" aria-label="Agora não" onClick={dismiss}>×</button>
      <div className="ec-ic">✉️</div>
      <div className="ec-body">
        <strong>Confirme seu e-mail</strong>
        <span>Pra garantir seu acesso (e poder entrar por e-mail se trocar de celular).</span>
        <div className="ec-row">
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            placeholder="voce@exemplo.com"
            value={email}
            onChange={(ev) => {
              setEmail(ev.target.value);
              if (state === "error") setState("ask");
            }}
          />
          <button className="ib-btn" onClick={save} disabled={state === "saving"}>
            {state === "saving" ? "…" : "Salvar"}
          </button>
        </div>
        {state === "error" && <span className="ec-err">{msg}</span>}
      </div>
    </section>
  );
}
