"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getHome, type TodaySession, type WorkoutStep } from "@/lib/api";

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
    return s.distance_m >= 1000
      ? `${(s.distance_m / 1000).toString().replace(".", ",")} km`
      : `${s.distance_m} m`;
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

export default function TreinoPage() {
  const router = useRouter();
  const [session, setSession] = useState<TodaySession | null>(null);
  const [loading, setLoading] = useState(true);
  const [place, setPlace] = useState<"livre" | "esteira">("livre");
  const [startMsg, setStartMsg] = useState(false);

  useEffect(() => {
    (async () => {
      const home = await getHome();
      if (!home) {
        router.replace("/entrar");
        return;
      }
      setSession(home.today.session);
      setLoading(false);
    })();
  }, [router]);

  if (loading) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // numeração contínua dos passos (incluindo dentro do "repetir")
  let n = 0;
  const rows: React.ReactNode[] = [];
  for (const s of session?.steps ?? []) {
    if (s.kind === "repeat" && s.steps) {
      rows.push(
        <div className="repeat" key={`r${rows.length}`}>
          <div className="repeat-head">
            <span className="rp">Repetir</span>
            <span className="xn">{s.reps}×</span>
          </div>
          <div className="blocks">
            {s.steps.map((c) => {
              n += 1;
              return <Step key={n} s={c} n={n} />;
            })}
          </div>
        </div>
      );
    } else {
      n += 1;
      rows.push(<Step key={n} s={s} n={n} />);
    }
  }

  return (
    <main className="stage">
      <div className="phone treino-screen has-nav">

        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="k">Treino de hoje</div><div className="t">Corrida</div></div>
          <span style={{ width: 34 }} />
        </header>

        {!session ? (
          <div className="card center">
            <h2 style={{ fontFamily: "var(--font-display)", margin: "0 0 6px" }}>Dia de descanso</h2>
            <p className="muted" style={{ margin: 0 }}>Sem treino no plano hoje. Recuperar também é treinar. 😴</p>
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
              <div className="toggle" role="group" aria-label="Local do treino">
                <button className={place === "livre" ? "on" : ""} onClick={() => setPlace("livre")}>Ar livre</button>
                <button className={place === "esteira" ? "on" : ""} onClick={() => setPlace("esteira")}>Esteira</button>
              </div>
            </div>

            <div className="blocks">{rows}</div>

            <div className="actions">
              <button className="btn-primary" onClick={() => setStartMsg(true)}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4" /></svg>
                Começar treino
              </button>
              {startMsg && (
                <div className="notice ok">Em breve: cronômetro guiado no app. Por enquanto, manda ver e o coach analisa depois pelo relógio/Strava. 👊</div>
              )}
            </div>
          </>
        )}

      </div>
      <BottomNav />
    </main>
  );
}
