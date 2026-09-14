"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getWorkouts, type TodaySession, type WorkoutDay, type WorkoutStep } from "@/lib/api";

const STEP_PT: Record<string, string> = {
  warmup: "Aquecimento",
  cooldown: "Desaquecimento",
  run: "Rodagem",
  interval: "Tiro forte",
  recovery: "Recuperação",
  rest: "Descanso",
};

function kindColor(kind: string): string {
  if (kind === "interval") return "hard";
  if (kind === "recovery") return "rec";
  if (kind === "rest") return "walk";
  return "warm";
}

function amount(s: WorkoutStep): string {
  if (s.distance_m != null)
    return s.distance_m >= 1000 ? `${(s.distance_m / 1000).toString().replace(".", ",")} km` : `${s.distance_m} m`;
  if (s.duration_sec != null)
    return s.duration_sec >= 60 ? `${Math.round(s.duration_sec / 60)} min` : `${s.duration_sec}s`;
  return "livre";
}

function pace(s: WorkoutStep): string {
  if (s.pace_min && s.pace_max) return `${s.pace_min}–${s.pace_max}`;
  if (s.pace_min) return s.pace_min;
  return "leve";
}

function Step({ s, n }: { s: WorkoutStep; n: number }) {
  const c = kindColor(s.kind);
  return (
    <div className="tstep">
      <span className={`stripe ${c}`} />
      <span className="idx">{n}</span>
      <div className="main">
        <div className="t">{STEP_PT[s.kind] ?? s.kind}</div>
        <div className="d">{amount(s)}</div>
      </div>
      <span className={`chip ${c}`}>{pace(s)}</span>
    </div>
  );
}

function DetalheInner() {
  const router = useRouter();
  const params = useSearchParams();
  const dayParam = params.get("day");

  const [day, setDay] = useState<WorkoutDay | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const w = await getWorkouts();
      if (!w) {
        router.replace("/entrar");
        return;
      }
      const picked =
        (dayParam && w.week.find((d) => d.day_en === dayParam)) ||
        w.week.find((d) => d.is_today) ||
        null;
      setDay(picked ?? null);
      setLoading(false);
    })();
  }, [router, dayParam]);

  if (loading) {
    return <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>;
  }

  const session: TodaySession | null = day?.session ?? null;

  let n = 0;
  const rows: React.ReactNode[] = [];
  for (const s of session?.steps ?? []) {
    if (s.kind === "repeat" && s.steps) {
      rows.push(
        <div className="repeat" key={`r${rows.length}`}>
          <div className="repeat-head"><span className="rp">Repetir</span><span className="xn">{s.reps}×</span></div>
          <div className="blocks">{s.steps.map((c) => { n += 1; return <Step key={n} s={c} n={n} />; })}</div>
        </div>
      );
    } else {
      n += 1;
      rows.push(<Step key={n} s={s} n={n} />);
    }
  }

  return (
    <>
      <header className="appbar">
        <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/treino")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </button>
        <div className="title"><div className="k">{day ? `${day.day_pt} · ${day.date_num}` : "Treino"}</div><div className="t">{session ? "Corrida" : "Descanso"}</div></div>
        <span style={{ width: 34 }} />
      </header>

      {!session ? (
        <div className="card center">
          <h2 style={{ fontFamily: "var(--font-display)", margin: "0 0 6px" }}>Dia de descanso</h2>
          <p className="muted" style={{ margin: 0 }}>Sem treino no plano nesse dia. 😴</p>
        </div>
      ) : (
        <>
          <div>
            <div className="kicker"><span className="pill">{session.workout_type}</span></div>
            <h1>{session.workout_type}{session.distance_km ? ` · ${String(session.distance_km).replace(".", ",")} km` : ""}</h1>
            <p className="intro">{session.objective}</p>
          </div>

          <div className="qstats">
            <div className="qstat"><div className="v">{session.distance_km ? String(session.distance_km).replace(".", ",") : "—"}<small> km</small></div><div className="k">Distância</div></div>
            <div className="qstat"><div className="v">{session.pace_min ?? "—"}<small>{session.pace_min ? "/km" : ""}</small></div><div className="k">Pace-alvo</div></div>
            <div className="qstat"><div className="v">{session.steps.length}</div><div className="k">Blocos</div></div>
          </div>

          <div className="topbar" style={{ marginTop: 2 }}>
            <span className="eyebrow">Blocos de treino</span>
          </div>

          <div className="blocks">{rows}</div>

          <button className="btn-primary" style={{ marginTop: 6 }} onClick={() => router.push("/correr")}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4" /></svg>
            Começar corrida
          </button>
        </>
      )}
    </>
  );
}

export default function DetalhePage() {
  return (
    <main className="stage">
      <div className="phone treino-screen">
        <Suspense fallback={<div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>}>
          <DetalheInner />
        </Suspense>
      </div>
    </main>
  );
}
