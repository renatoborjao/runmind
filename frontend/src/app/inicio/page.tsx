"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  getHome,
  getMe,
  logout,
  type HomeSummary,
  type WorkoutStep,
} from "@/lib/api";

const RING_C = 2 * Math.PI * 47; // circunferência do anel de prontidão

function fmtSleep(h: number | null): string {
  if (h == null) return "—";
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return `${hh}:${String(mm).padStart(2, "0")}`;
}

function readinessVerdict(score: number): { badge: string; title: string; note: string } {
  if (score >= 75)
    return {
      badge: "Corpo descansado",
      title: "Pode dar ritmo hoje.",
      note: "Bateria cheia e recuperação em dia. Aproveita o treino.",
    };
  if (score >= 50)
    return {
      badge: "Corpo ok",
      title: "Dá pra treinar, sem exagero.",
      note: "Recuperação parcial — segura a intensidade se pedir.",
    };
  return {
    badge: "Corpo pedindo cautela",
    title: "Hoje é dia de segurar.",
    note: "Recuperação baixa. Prioriza leveza ou descanso.",
  };
}

const STEP_PT: Record<string, string> = {
  warmup: "Aquecimento",
  cooldown: "Desaquecimento",
  run: "Rodagem",
  interval: "Tiro forte",
  recovery: "Recuperação",
  rest: "Descanso",
};

function stepAmount(s: WorkoutStep): string {
  if (s.distance_m != null)
    return s.distance_m >= 1000
      ? `${(s.distance_m / 1000).toString().replace(".", ",")} km`
      : `${s.distance_m} m`;
  if (s.duration_sec != null)
    return s.duration_sec >= 60
      ? `${Math.round(s.duration_sec / 60)} min`
      : `${s.duration_sec}s`;
  return "";
}

function stepPace(s: WorkoutStep): string {
  if (s.pace_min && s.pace_max) return `${s.pace_min}–${s.pace_max}`;
  if (s.pace_min) return s.pace_min;
  if (s.kind === "recovery" || s.kind === "rest") return "leve";
  return "";
}

// achata os passos em linhas renderizáveis (grupos repeat viram cabeçalho + filhos)
function flattenSteps(steps: WorkoutStep[]): { label: string; amount: string; pace: string; header?: string }[] {
  const rows: { label: string; amount: string; pace: string; header?: string }[] = [];
  let n = 0;
  for (const s of steps) {
    if (s.kind === "repeat" && s.steps) {
      rows.push({ label: "", amount: "", pace: "", header: `Repetir ${s.reps}×` });
      for (const c of s.steps) {
        n += 1;
        rows.push({ label: `${n}. ${STEP_PT[c.kind] ?? c.kind}`, amount: stepAmount(c), pace: stepPace(c) });
      }
    } else {
      n += 1;
      rows.push({ label: `${n}. ${STEP_PT[s.kind] ?? s.kind}`, amount: stepAmount(s), pace: stepPace(s) });
    }
  }
  return rows;
}

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 12h4l2.5-7 4 15 2.5-8H22" />
      </svg>
    </span>
  );
}

export default function InicioPage() {
  const router = useRouter();
  const [home, setHome] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const who = await getMe();
      if (!who) {
        router.replace("/entrar");
        return;
      }
      setHome(await getHome());
      setLoading(false);
    })();
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/entrar");
  }

  if (loading || !home) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const firstName = (home.athlete.name ?? "").split(" ")[0] || "corredor";
  const body = home.body;
  const session = home.today.session;
  const fitness = home.fitness;
  const shoe = home.shoe;

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
          <a className="link" onClick={onLogout}>Sair</a>
        </div>

        <div className="greet">
          <h1>Olá, {firstName}.</h1>
          <p>{home.today.weekday_pt} · {home.today.date_label}</p>
        </div>

        {/* PRONTIDÃO (anel: prontidão do Garmin ou, na falta, bateria ao acordar) */}
        {body && body.ring && (() => {
          const v = readinessVerdict(body.ring.value);
          return (
            <section className="card hero">
              <div className="hero-top">
                <div className="ring" role="img" aria-label={`${body.ring.label} ${body.ring.value}`}>
                  <svg width="108" height="108" viewBox="0 0 108 108">
                    <circle cx="54" cy="54" r="47" fill="none" stroke="var(--line)" strokeWidth="9" />
                    <circle cx="54" cy="54" r="47" fill="none" stroke="var(--accent)" strokeWidth="9" strokeLinecap="round"
                      strokeDasharray={RING_C} strokeDashoffset={RING_C * (1 - body.ring.value / 100)} />
                  </svg>
                  <div className="ring-center">
                    <div className="num">{body.ring.value}</div>
                    <div className="den">{body.ring.label}</div>
                  </div>
                </div>
                <div className="hero-verdict">
                  <span className="badge"><span className="dot" />{v.badge}</span>
                  <h2>{v.title}</h2>
                  <p>{v.note}</p>
                </div>
              </div>
              <div className="vitals">
                <div className="vital"><div className="k">Bateria</div><div className="v">{body.body_battery_at_wake ?? "—"}</div><div className="u">ao acordar</div></div>
                <div className="vital"><div className="k">Sono</div><div className="v">{fmtSleep(body.sleep_hours)}</div><div className="u">horas</div></div>
                <div className="vital"><div className="k">FC rep.</div><div className="v">{body.resting_hr ?? "—"}</div><div className="u">bpm</div></div>
                <div className="vital"><div className="k">Resp.</div><div className="v">{body.respiration_sleep_avg != null ? Math.round(body.respiration_sleep_avg) : "—"}</div><div className="u">rpm</div></div>
              </div>
            </section>
          );
        })()}

        {/* corpo sem anel, mas com métricas soltas */}
        {body && !body.ring && (body.sleep_hours != null || body.resting_hr != null) && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Seu corpo hoje</span></div>
            <div className="vitals">
              <div className="vital"><div className="k">Bateria</div><div className="v">{body.body_battery_at_wake ?? "—"}</div><div className="u">ao acordar</div></div>
              <div className="vital"><div className="k">Sono</div><div className="v">{fmtSleep(body.sleep_hours)}</div><div className="u">horas</div></div>
              <div className="vital"><div className="k">FC rep.</div><div className="v">{body.resting_hr ?? "—"}</div><div className="u">bpm</div></div>
              <div className="vital"><div className="k">Resp.</div><div className="v">{body.respiration_sleep_avg != null ? Math.round(body.respiration_sleep_avg) : "—"}</div><div className="u">rpm</div></div>
            </div>
          </section>
        )}

        {/* TREINO DE HOJE */}
        <section className={`card today${session ? " tap" : ""}`} onClick={session ? () => router.push("/treino/detalhe") : undefined}>
          <div className="card-head">
            <span className="eyebrow">Treino de hoje</span>
            {session && (session.pace_min && session.pace_max) && (
              <span className="pace-pill">{session.pace_min}–{session.pace_max}/km</span>
            )}
          </div>
          {session ? (
            <>
              <h2>{session.workout_type}{session.distance_km ? ` · ${String(session.distance_km).replace(".", ",")} km` : ""}</h2>
              <p className="sub">{session.objective}</p>
              {session.steps.length > 0 && (
                <div className="steps">
                  {flattenSteps(session.steps).map((r, i) =>
                    r.header ? (
                      <div className="step" key={i}><span className="eyebrow" style={{ color: "var(--rose)" }}>{r.header}</span></div>
                    ) : (
                      <div className="step" key={i}>
                        <div style={{ flex: 1 }}>
                          <div className="t">{r.label}</div>
                          {r.amount && <div className="d"><b>{r.amount}</b></div>}
                        </div>
                        {r.pace && <span className="d" style={{ fontFamily: "var(--font-mono)" }}>{r.pace}</span>}
                      </div>
                    )
                  )}
                </div>
              )}
              <button className="cta-btn" onClick={(e) => { e.stopPropagation(); router.push("/treino/detalhe"); }}>
                Ver treino completo
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
            </>
          ) : (
            <>
              <h2>Dia de descanso</h2>
              <p className="sub" style={{ margin: 0 }}>Sem treino no plano hoje. Recuperar também é treinar. 😴</p>
            </>
          )}
        </section>

        {/* SEMANA */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Sua semana</span></div>
          <div className="week">
            {home.week.map((d, i) => (
              <div key={i} className={`day${d.is_today ? " today" : ""}${d.workout_type ? "" : " rest"}`}>
                <div className="dn">{d.day_pt.toUpperCase()}</div>
                <div className="dd">{d.date_num}</div>
                <span className={`sesh ${d.kind ?? "off"}`} />
              </div>
            ))}
          </div>
          <div className="legend">
            <span><i style={{ background: "var(--rose)" }} />Tiro</span>
            <span><i style={{ background: "var(--accent)" }} />Rodagem</span>
            <span><i style={{ background: "#E1911A" }} />Longão</span>
            <span><i style={{ background: "var(--muted)" }} />Descanso</span>
          </div>
        </section>

        {/* EVOLUÇÃO */}
        {fitness && (fitness.vo2max != null || fitness.projection_10k) && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Evolução</span></div>
            <div className="prog-grid">
              {fitness.projection_10k && (
                <div className="stat">
                  <div className="k">Projeção 10 km</div>
                  <div className="big">{fitness.projection_10k}</div>
                </div>
              )}
              {fitness.vo2max != null && (
                <div className="stat">
                  <div className="k">VO₂max</div>
                  <div className="big">{fitness.vo2max} <small>ml/kg</small></div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* TÊNIS */}
        {shoe && (
          <section className="card">
            <div className="shoe">
              <span className="shoe-ico" aria-hidden>
                <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-ink)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 17h18a2 2 0 0 0 2-2c0-1-.7-1.7-1.7-2L13 10 9.5 6 6 6l-.5 4.5L2 13z" /><path d="M2 13v4" /></svg>
              </span>
              <div style={{ flex: 1 }}>
                <div className="n">{shoe.name}</div>
                <div className="km">{shoe.total_km} / {shoe.alert_threshold_km} km · troca em ~{shoe.remaining_km} km</div>
                <div className="wear"><i style={{ width: `${shoe.pct}%` }} /></div>
              </div>
            </div>
          </section>
        )}

        <p className="muted center" style={{ marginTop: 2 }}>Ritmind · {home.athlete.goal}</p>

      </div>
      <BottomNav />
    </main>
  );
}
