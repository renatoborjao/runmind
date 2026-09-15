"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getCoachMessages, sendCoachMessage, type ChatMsg } from "@/lib/api";

const TELEGRAM_COACH = "https://t.me/runmind_coach_bot";

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

// rótulo do botão do cartão pelo destino
function actionLabel(url?: string | null): string {
  if (!url) return "Ver";
  if (url.startsWith("/treino")) return "Ver treino";
  if (url.startsWith("/atividades")) return "Ver atividade";
  if (url.startsWith("/evolucao")) return "Ver evolução";
  if (url.startsWith("/provas")) return "Ver provas";
  if (url.startsWith("/tenis")) return "Ver tênis";
  if (url.startsWith("/corpo")) return "Ver meu corpo";
  return "Abrir";
}

export default function CoachPage() {
  const router = useRouter();
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      const m = await getCoachMessages();
      if (m === null) { router.replace("/entrar"); return; }
      setMsgs(m);
      setLoading(false);
    })();
  }, [router]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, sending]);

  async function onSend() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text, at: null }]);
    setSending(true);
    const reply = await sendCoachMessage(text);
    setSending(false);
    setMsgs((m) => [
      ...m,
      { role: "assistant", text: reply ?? "Ops, não consegui responder agora. Tenta de novo daqui a pouco. 🙏", at: null },
    ]);
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <main className="stage">
      <div className="phone has-nav has-composer">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Coach</span></div>
          <a className="link" href={TELEGRAM_COACH} target="_blank" rel="noopener noreferrer">no Telegram ↗</a>
        </div>

        {loading ? (
          <p className="auth-sub center" style={{ margin: "30px 0" }}>Carregando…</p>
        ) : msgs.length === 0 ? (
          <p className="chat-empty">Fala com teu coach 👋<br />Pergunta sobre teu treino, como tá teu corpo, ou peça um ajuste.</p>
        ) : (
          <div className="chat-msgs">
            {msgs.map((m, i) => {
              if (m.role === "coach") {
                const hasAction = !!m.url && m.url !== "/inicio/";
                return (
                  <div key={i} className="coach-card">
                    {m.title && <div className="cc-title">{m.title}</div>}
                    <div className="cc-text">{m.text}</div>
                    {hasAction && (
                      <button className="cc-action" onClick={() => router.push(m.url!)}>
                        {actionLabel(m.url)}
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
                      </button>
                    )}
                  </div>
                );
              }
              return (
                <div key={i} className={`msg ${m.role === "user" ? "user" : "bot"}`}>{m.text}</div>
              );
            })}
            {sending && <div className="msg bot typing">Coach digitando…</div>}
            <div ref={endRef} />
          </div>
        )}

      </div>

      <div className="composer">
        <textarea
          rows={1}
          placeholder="Fala com teu coach…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
        />
        <button className="send-btn" onClick={onSend} disabled={sending || !input.trim()} aria-label="Enviar">
          <svg viewBox="0 0 24 24" fill="none" stroke="#04231d" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h15M13 6l6 6-6 6" /></svg>
        </button>
      </div>

      <BottomNav />
    </main>
  );
}
