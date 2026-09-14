"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import NotifBell from "../notif-bell";
import InstallBanner from "../install-banner";
import {
  getBody,
  getHome,
  getMe,
  getProgress,
  type BodyReading,
  type HomeSummary,
  type Progress,
  type TodaySession,
  type WorkoutStep,
} from "@/lib/api";

const RING_C = 2 * Math.PI * 47; // circunferência do anel de prontidão

const TONE_COLOR: Record<string, string> = {
  good: "var(--accent)",
  warn: "#F5A623",
  bad: "var(--rose)",
};

// Veredito do herói. Preferimos SEMPRE a leitura REAL do corpo (backend, ciente
// do histórico: estado + tom + limitador) e amarramos ao treino de hoje. Só
// caímos no veredito raso pelo número do anel quando não há leitura de corpo —
// assim a home nunca "decide no vácuo" nem diverge da tela /corpo.
function heroVerdict(
  bd: BodyReading | null,
  session: TodaySession | null,
  ringVal: number,
): { badge: string; title: string; note: string; tone: string } {
  if (bd?.has_data && bd.state_label) {
    const tone = bd.tone ?? "warn";
    const hard = !!session && (session.kind === "tiro" || session.kind === "long");
    const title =
      tone === "good"
        ? "Corpo pronto pra treinar."
        : tone === "warn"
          ? "Dá pra treinar, com cautela."
          : "Hoje é dia de segurar.";
    let note: string;
    if (tone === "bad") {
      note = hard
        ? "Treino forte no plano. Se o corpo não responder, fala com o coach pra ajustar."
        : "Recuperação baixa — prioriza leveza ou descanso.";
    } else if (tone === "warn") {
      note = hard
        ? "Treino forte hoje: começa no controle e vê como o corpo responde."
        : "Corpo absorvendo carga. Treina sem forçar.";
    } else {
      note = session
        ? "Recuperação em dia. Pode aproveitar o treino de hoje."
        : "Recuperação em dia. Bom dia pra descansar bem.";
    }
    if (bd.limiter_label) note += ` Ponto de atenção: ${bd.limiter_label.toLowerCase()}.`;
    return { badge: bd.state_label, title, note, tone };
  }
  const v = readinessVerdict(ringVal);
  const tone = ringVal >= 75 ? "good" : ringVal >= 50 ? "warn" : "bad";
  return { ...v, tone };
}

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

// mini-gráfico de volume semanal pra home: barras compactas, última semana
// esmaecida (em curso). Mesmo desenho da tela de evolução, só que menor.
function MiniVolume({ data }: { data: { label: string; km: number }[] }) {
  const W = 320, H = 88, padB = 16, padT = 14;
  const max = Math.max(10, ...data.map((d) => d.km));
  const n = data.length;
  const gap = 8;
  const bw = (W - gap * (n - 1)) / n;
  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Volume por semana">
        {data.map((d, i) => {
          const h = d.km > 0 ? ((H - padB - padT) * d.km) / max : 0;
          const x = i * (bw + gap);
          const y = H - padB - h;
          const last = i === n - 1;
          return (
            <g key={i}>
              {d.km > 0 && (
                <text x={x + bw / 2} y={y - 3} textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fill="var(--ink-soft)">{d.km}</text>
              )}
              <rect x={x} y={y} width={bw} height={Math.max(h, 1)} rx="3" fill={last ? "var(--muted)" : "var(--accent)"} opacity={last ? 0.5 : 1} />
              <text x={x + bw / 2} y={H - 5} textAnchor="middle" fontSize="7.5" fontFamily="var(--font-mono)" fill="var(--muted)">{d.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function InicioPage() {
  const router = useRouter();
  const [home, setHome] = useState<HomeSummary | null>(null);
  const [bodyR, setBodyR] = useState<BodyReading | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const who = await getMe();
      if (!who) {
        router.replace("/entrar");
        return;
      }
      const [h, bd, pr] = await Promise.all([getHome(), getBody(), getProgress()]);
      setHome(h);
      setBodyR(bd);
      setProg(pr);
      setLoading(false);
    })();
  }, [router]);

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
  const shoe = home.shoe;

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
          <div className="topbar-actions">
            <NotifBell />
            <button className="avatar-sm" aria-label="Perfil" onClick={() => router.push("/perfil")}>
              {home.athlete.avatar ? (
                <img className="avatar-img" src={home.athlete.avatar} alt="Perfil" />
              ) : (
                (home.athlete.name || "").trim().split(" ").map((w) => w[0]).slice(0, 2).join("") || "🏃"
              )}
            </button>
          </div>
        </div>

        <div className="greet">
          <h1>Olá, {firstName}.</h1>
          <p>{home.today.weekday_pt} · {home.today.date_label}</p>
        </div>

        <InstallBanner />

        {/* PRONTIDÃO (anel: prontidão do Garmin ou, na falta, bateria ao acordar) */}
        {body && body.ring && (() => {
          const v = heroVerdict(bodyR, session, body.ring.value);
          return (
            <section className="card hero tap" onClick={() => router.push("/corpo")}>
              <div className="hero-top">
                <div className="ring" role="img" aria-label={`${body.ring.label} ${body.ring.value}`}>
                  <svg width="108" height="108" viewBox="0 0 108 108">
                    <circle cx="54" cy="54" r="47" fill="none" stroke="var(--line)" strokeWidth="9" />
                    <circle cx="54" cy="54" r="47" fill="none" stroke={TONE_COLOR[v.tone]} strokeWidth="9" strokeLinecap="round"
                      strokeDasharray={RING_C} strokeDashoffset={RING_C * (1 - body.ring.value / 100)} />
                  </svg>
                  <div className="ring-center">
                    <div className="num">{body.ring.value}</div>
                    <div className="den">{body.ring.label}</div>
                  </div>
                </div>
                <div className="hero-verdict">
                  <span className="badge"><span className="dot" style={{ background: TONE_COLOR[v.tone] }} />{v.badge}</span>
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
          <section className="card tap" onClick={() => router.push("/corpo")}>
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
        <section className={`card today${session ? " tap" : ""}`} onClick={session ? () => router.push(`/treino/detalhe?day=${home.today.day_en}`) : undefined}>
          <div className="card-head">
            <span className="eyebrow">{home.today.label}{home.today.session_date_label ? ` · ${home.today.session_date_label}` : ""}</span>
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
              <button className="cta-btn" onClick={(e) => { e.stopPropagation(); router.push(`/treino/detalhe?day=${home.today.day_en}`); }}>
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

        {/* CORRER AGORA */}
        <button className="cta-btn" onClick={() => router.push("/correr")}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" /></svg>
          Correr agora (GPS)
        </button>
        <a className="link center" style={{ display: "block", marginTop: -2 }} onClick={() => router.push("/atividades")}>Minhas atividades</a>

        {/* SEMANA */}
        <section className="card">
          <div className="card-head">
            <span className="eyebrow">Sua semana</span>
            <a className="link" onClick={() => router.push("/treino")}>Calendário</a>
          </div>

          <div className="week">
            {home.week.map((d, i) => (
              <div
                key={i}
                className={`day${d.is_today ? " today" : ""}${d.workout_type ? " tap" : " rest"}`}
                onClick={d.workout_type ? () => router.push(`/treino/detalhe?day=${d.day_en}`) : undefined}
              >
                <div className="dn">{d.day_pt.toUpperCase()}</div>
                <div className="dd">{d.date_num}</div>
                {d.workout_type ? (
                  <span className="sesh" style={{ background: d.done ? "var(--accent)" : "#F5A623" }} />
                ) : (
                  <span className="sesh" style={{ background: "transparent" }} />
                )}
              </div>
            ))}
          </div>

          <div className="legend" style={{ marginBottom: 6 }}>
            <span><i style={{ background: "var(--accent)" }} />Feito</span>
            <span><i style={{ background: "#F5A623" }} />A fazer</span>
          </div>

          {home.week.filter((d) => d.workout_type).map((d) => (
            <div key={d.day_en} className="wrow" onClick={() => router.push(`/treino/detalhe?day=${d.day_en}`)}>
              <div className="date">
                <div className="dn">{d.day_pt}</div>
                <div className="dd">{d.date_num}</div>
              </div>
              <span className="kdot" style={{ background: d.done ? "var(--accent)" : "#F5A623" }} />
              <div className="info">
                <div className="wt">{d.workout_type}{d.distance_km ? ` · ${String(d.distance_km).replace(".", ",")} km` : ""}</div>
                <div className="wd">{d.done ? "feito ✓" : d.is_today ? "é hoje" : "a fazer"}</div>
              </div>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
            </div>
          ))}
        </section>

        {/* EVOLUÇÃO — teaser com substância: jornada + volume + projeções */}
        {prog && (prog.journey.runs > 0 || prog.fitness.vo2max != null) && (
          <section className="card tap" onClick={() => router.push("/evolucao")}>
            <div className="card-head">
              <span className="eyebrow">Evolução</span>
              <a className="link" onClick={(e) => { e.stopPropagation(); router.push("/evolucao"); }}>Ver tudo</a>
            </div>

            <div className="prog-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div className="stat"><div className="k">Km no Ritmind</div><div className="big">{prog.journey.km_total}</div></div>
              <div className="stat"><div className="k">Treinos</div><div className="big">{prog.journey.runs}</div></div>
              <div className="stat"><div className="k">Maior</div><div className="big">{String(prog.journey.biggest_km).replace(".", ",")}<small> km</small></div></div>
            </div>

            {prog.weekly_volume && prog.weekly_volume.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <span className="eyebrow" style={{ display: "block", marginBottom: 2 }}>Volume por semana (km)</span>
                <MiniVolume data={prog.weekly_volume.slice(-6)} />
              </div>
            )}

            {(prog.fitness.vo2max != null || prog.fitness.projection_5k || prog.fitness.projection_10k || prog.fitness.projection_half) && (
              <div className="ev-foot">
                {prog.fitness.vo2max != null && <span className="ev-chip">VO₂max <b>{prog.fitness.vo2max}</b></span>}
                {prog.fitness.projection_5k && <span className="ev-chip">5k <b>{prog.fitness.projection_5k}</b></span>}
                {prog.fitness.projection_10k && <span className="ev-chip">10k <b>{prog.fitness.projection_10k}</b></span>}
                {prog.fitness.projection_half && <span className="ev-chip">Meia <b>{prog.fitness.projection_half}</b></span>}
              </div>
            )}
          </section>
        )}

        {/* TÊNIS */}
        {shoe ? (
          <section className="card tap" onClick={() => router.push("/tenis")}>
            <div className="card-head"><span className="eyebrow">Tênis em uso</span><a className="link" onClick={(e) => { e.stopPropagation(); router.push("/tenis"); }}>Armário</a></div>
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
        ) : (
          <button className="cta-btn" onClick={() => router.push("/tenis")}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 17h18a2 2 0 0 0 2-2c0-1-.7-1.7-1.7-2L13 10 9.5 6 6 6l-.5 4.5L2 13z" /><path d="M2 13v4" /></svg>
            Montar meu armário de tênis
          </button>
        )}

        <p className="muted center" style={{ marginTop: 2 }}>Ritmind · {home.athlete.goal}</p>

      </div>
      <BottomNav />
    </main>
  );
}
