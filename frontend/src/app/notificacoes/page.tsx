"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  getNotifications,
  markNotificationsRead,
  type AppNotification,
} from "@/lib/api";
import { pushState, requestPush, type PushState } from "@/lib/push";

function fmtWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "agora";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  if (diff < 172800) return "ontem";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

// ícone por tipo — só um toque visual; cai num sino genérico
function iconFor(kind: string | null): string {
  if (!kind) return "🔔";
  if (kind.includes("record")) return "🏅";
  if (kind.startsWith("race")) return "🏁";
  if (kind === "feedback") return "📊";
  if (kind === "daily_training" || kind === "weekly_plan") return "🏃";
  if (kind === "morning_briefing") return "☀️";
  if (kind === "wear_alert") return "👟";
  if (kind === "weekly_review" || kind === "monthly_recap") return "📅";
  if (kind === "reengagement") return "👋";
  if (kind === "strava_connect") return "🔄";
  return "🔔";
}

export default function NotificacoesPage() {
  const router = useRouter();
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [unreadIds, setUnreadIds] = useState<Set<string>>(new Set());
  const [pstate, setPstate] = useState<PushState>("unsupported");

  useEffect(() => {
    setPstate(pushState());
    (async () => {
      const r = await getNotifications();
      if (r === null) { router.replace("/entrar"); return; }
      setItems(r.items);
      // guarda quais estavam não-lidas pra mostrar o ponto nesta sessão
      setUnreadIds(new Set(r.items.filter((i) => !i.read).map((i) => i.id)));
      // abriu a central = leu: zera o badge no servidor
      if (r.unread > 0) markNotificationsRead().catch(() => {});
    })();
  }, [router]);

  async function enablePush() {
    const s = await requestPush();
    setPstate(s);
  }

  if (items === null) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="stage">
      <div className="phone has-nav">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Notificações</div></div>
          <span style={{ width: 34 }} />
        </header>

        {/* CTA de push: só quando dá pra pedir permissão */}
        {pstate === "default" && (
          <section className="card push-cta">
            <div className="push-cta-txt">
              <strong>Ative as notificações</strong>
              <span>Receba no celular o treino do dia, análises e recordes — mesmo com o app fechado.</span>
            </div>
            <button className="btn" onClick={enablePush}>Ativar</button>
          </section>
        )}
        {pstate === "denied" && (
          <p className="muted" style={{ margin: "0 0 4px", fontSize: 13 }}>
            Notificações bloqueadas nas configurações do navegador. Libere pra receber os toques no celular.
          </p>
        )}

        {items.length === 0 ? (
          <div className="empty-state">
            <div className="emoji">🔔</div>
            <p>Sem novidades por aqui ainda. Seus toques do coach aparecem nesta tela.</p>
          </div>
        ) : (
          <div className="notif-list">
            {items.map((n) => (
              <div key={n.id} className={`notif-row${unreadIds.has(n.id) ? " unread" : ""}`}>
                <div className="notif-ic">{iconFor(n.kind)}</div>
                <div className="notif-body">
                  <div className="notif-head">
                    <span className="notif-title">{n.title || "Mensagem do coach"}</span>
                    <span className="notif-when">{fmtWhen(n.created_at)}</span>
                  </div>
                  <p className="notif-text">{n.text}</p>
                </div>
                {unreadIds.has(n.id) && <span className="notif-dot" aria-label="não lida" />}
              </div>
            ))}
          </div>
        )}

        <BottomNav />
      </div>
    </main>
  );
}
