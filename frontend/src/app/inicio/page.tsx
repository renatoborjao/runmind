"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, getPlan, logout, type Me } from "@/lib/api";

const DAY_PT: Record<string, string> = {
  Monday: "Seg",
  Tuesday: "Ter",
  Wednesday: "Qua",
  Thursday: "Qui",
  Friday: "Sex",
  Saturday: "Sáb",
  Sunday: "Dom",
};

interface Session {
  day: string;
  workout_type: string;
}

export default function InicioPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const who = await getMe();
      if (!who) {
        router.replace("/entrar");
        return;
      }
      setMe(who);
      const plan = await getPlan();
      setSessions(plan?.plan?.sessions ?? []);
      setLoading(false);
    })();
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/entrar");
  }

  if (loading) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const firstName = (me?.name ?? "").split(" ")[0] || "corredor";

  return (
    <main className="stage">
      <div className="phone">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div className="brand">
            <span className="mark" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 12h4l2.5-7 4 15 2.5-8H22" />
              </svg>
            </span>
            <span className="word">Rit<b>mind</b></span>
          </div>
          <a className="link" onClick={onLogout}>Sair</a>
        </div>

        <div>
          <h1 className="auth-title">Bom dia, {firstName}.</h1>
          <p className="auth-sub" style={{ margin: 0 }}>🎯 {me?.goal}</p>
        </div>

        <div className="card">
          <p className="font-mono" style={{ fontSize: 10.5, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--muted)", margin: "0 0 12px" }}>
            Sua semana
          </p>
          {sessions && sessions.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {sessions.map((s, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span className="font-mono" style={{ fontSize: 11, fontWeight: 600, color: "var(--accent-ink)", background: "var(--accent-wash)", padding: "4px 8px", borderRadius: 8, minWidth: 42, textAlign: "center" }}>
                    {DAY_PT[s.day] ?? s.day}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{s.workout_type}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>Seu plano da semana aparece aqui.</p>
          )}
        </div>

        <p className="muted center">A home completa chega na próxima fatia. 🏗️</p>
      </div>
    </main>
  );
}
