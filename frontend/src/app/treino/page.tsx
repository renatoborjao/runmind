"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getWorkouts, type WorkoutsResponse } from "@/lib/api";

const KIND_COLOR: Record<string, string> = {
  tiro: "var(--rose)",
  rod: "var(--accent)",
  long: "#E1911A",
};

const WEEKDAY_HEAD = ["D", "S", "T", "Q", "Q", "S", "S"];
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

export default function TreinoPage() {
  const router = useRouter();
  const [w, setW] = useState<WorkoutsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const data = await getWorkouts();
      if (!data) {
        router.replace("/entrar");
        return;
      }
      setW(data);
      setLoading(false);
    })();
  }, [router]);

  // mapa data_iso -> {kind, day_en} pros dias com treino
  const byDate = useMemo(() => {
    const m = new Map<string, { kind: string; day_en: string }>();
    w?.week.forEach((d) => {
      if (d.session) m.set(d.date_iso, { kind: d.session.kind, day_en: d.day_en });
    });
    return m;
  }, [w]);

  if (loading || !w) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const todayIso = `${year}-${String(month + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const raceIso = w.race?.date_iso ?? null;

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const sessions = w.week.filter((d) => d.session);

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>

        <div className="greet">
          <h1>Treinos</h1>
          <p style={{ textTransform: "capitalize" }}>{MONTHS[month]} de {year}</p>
        </div>

        {/* prova */}
        {w.race && (
          <section className="card">
            <div className="race">
              <div className="cd">
                <div className="n">{w.race.days_until >= 0 ? w.race.days_until : "—"}</div>
                <div className="l">{w.race.days_until === 1 ? "dia" : "dias"}</div>
              </div>
              <div className="info">
                <div className="rn">🏁 {w.race.name}</div>
                <div className="rd">
                  {new Date(w.race.date_iso + "T00:00:00").toLocaleDateString("pt-BR")}
                  {w.race.target_time ? ` · alvo ${w.race.target_time}` : ""}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* calendário do mês */}
        <section className="card">
          <div className="cal-head">
            {WEEKDAY_HEAD.map((h, i) => <span key={i}>{h}</span>)}
          </div>
          <div className="cal-grid">
            {cells.map((d, i) => {
              if (d === null) return <div key={i} className="cal-cell empty" />;
              const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
              const s = byDate.get(iso);
              const isToday = iso === todayIso;
              const isRace = iso === raceIso;
              return (
                <div
                  key={i}
                  className={`cal-cell${s ? " has" : ""}${isToday ? " today" : ""}`}
                  onClick={s ? () => router.push(`/treino/detalhe?day=${s.day_en}`) : undefined}
                >
                  {isRace && <span className="flag">🏁</span>}
                  <span>{d}</span>
                  {s && <span className="cdot" style={{ background: KIND_COLOR[s.kind] ?? "var(--accent)" }} />}
                </div>
              );
            })}
          </div>
          <div className="legend">
            <span><i style={{ background: "var(--rose)" }} />Tiro</span>
            <span><i style={{ background: "var(--accent)" }} />Rodagem</span>
            <span><i style={{ background: "#E1911A" }} />Longão</span>
          </div>
        </section>

        {/* lista da semana */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Treinos da semana</span></div>
          {sessions.length > 0 ? (
            sessions.map((d) => (
              <div key={d.day_en} className="wrow" onClick={() => router.push(`/treino/detalhe?day=${d.day_en}`)}>
                <div className="date">
                  <div className="dn">{d.day_pt}</div>
                  <div className="dd">{d.date_num}</div>
                </div>
                <span className="kdot" style={{ background: KIND_COLOR[d.session!.kind] ?? "var(--accent)" }} />
                <div className="info">
                  <div className="wt">{d.session!.workout_type}{d.session!.distance_km ? ` · ${String(d.session!.distance_km).replace(".", ",")} km` : ""}</div>
                  <div className="wd">{d.session!.pace_min && d.session!.pace_max ? `${d.session!.pace_min}–${d.session!.pace_max}/km` : "no seu ritmo"}</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
              </div>
            ))
          ) : (
            <p className="muted" style={{ margin: 0 }}>Sem treinos planejados nesta semana.</p>
          )}
        </section>

      </div>
      <BottomNav />
    </main>
  );
}
