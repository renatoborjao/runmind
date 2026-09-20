"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getBody, type BodyReading, type BodyTrend } from "@/lib/api";

function fmtSleep(h: number | null | undefined): string {
  if (h == null) return "—";
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return `${hh}:${String(mm).padStart(2, "0")}`;
}

function lastReal(a: (number | null)[]): number | null {
  for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i];
  return null;
}

// linha fina dos últimos dias; cor pela DIREÇÃO (verde=melhora, âmbar=piora)
// conforme upIsGood — a mesma convenção das setas de HRV/FC.
function Sparkline({ data, upIsGood }: { data: (number | null)[]; upIsGood: boolean }) {
  const W = 92, H = 30, pad = 4;
  const real = data.map((v, i) => ({ v, i })).filter((p) => p.v != null) as { v: number; i: number }[];
  if (real.length < 2) return null;
  const vs = real.map((p) => p.v);
  const min = Math.min(...vs), max = Math.max(...vs), span = max - min || 1;
  const n = data.length;
  const x = (i: number) => pad + (i / (n - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - min) / span) * (H - 2 * pad);
  const pts = real.map((p) => `${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const first = real[0].v, last = real[real.length - 1].v;
  const good = last === first ? null : (last > first) === upIsGood;
  const stroke = good == null ? "var(--muted)" : good ? "var(--accent)" : "#F5A623";
  const lp = real[real.length - 1];
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(lp.i)} cy={y(lp.v)} r="2.6" fill={stroke} />
    </svg>
  );
}

const TREND_ROWS: { key: keyof BodyTrend; label: string; upIsGood: boolean; fmt: (v: number) => string }[] = [
  { key: "readiness", label: "Prontidão", upIsGood: true, fmt: (v) => String(Math.round(v)) },
  { key: "battery", label: "Bateria ao acordar", upIsGood: true, fmt: (v) => String(Math.round(v)) },
  { key: "sleep_hours", label: "Sono", upIsGood: true, fmt: (v) => fmtSleep(v) },
  { key: "hrv", label: "HRV", upIsGood: true, fmt: (v) => `${Math.round(v)} ms` },
  { key: "resting_hr", label: "FC repouso", upIsGood: false, fmt: (v) => `${Math.round(v)} bpm` },
];

// conduta curta que apenas ROTULA a conclusão do backend (tom do estado),
// sem inventar julgamento — mesma leitura que a home mostra no herói.
function conduta(tone?: string): string {
  if (tone === "bad") return "Conduta: priorize leveza ou descanso até o corpo responder.";
  if (tone === "warn") return "Conduta: treine no controle, sem forçar a intensidade.";
  return "Conduta: corpo liberado — pode seguir o plano.";
}

// arrow + cor conforme a direção; upIsGood diz se subir é bom pra essa métrica
function Dir({ direction, upIsGood }: { direction?: string; upIsGood: boolean }) {
  if (!direction || direction === "stable") return null;
  const rising = direction === "rising";
  const good = rising === upIsGood;
  return <span className={`dir ${good ? "good" : "warn"}`}>{rising ? "↑" : "↓"}</span>;
}

// horas decimais → "6h 51" (compacto pra estágios do sono)
function fmtHM(h: number | null | undefined): string {
  if (h == null) return "—";
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return hh > 0 ? `${hh}h ${String(mm).padStart(2, "0")}` : `${mm}min`;
}

// faixas do score de sono do Garmin
function sleepScore(score: number): { tone: string; label: string } {
  if (score >= 90) return { tone: "good", label: "Excelente" };
  if (score >= 80) return { tone: "good", label: "Bom" };
  if (score >= 60) return { tone: "warn", label: "Razoável" };
  return { tone: "bad", label: "Ruim" };
}

// estágios do sono: chave no payload, rótulo e cor da barra empilhada
const SLEEP_STAGES: { key: "deep" | "light" | "rem" | "awake"; label: string; color: string }[] = [
  { key: "deep", label: "Profundo", color: "var(--accent)" },
  { key: "light", label: "Leve", color: "rgba(15,180,153,0.45)" },
  { key: "rem", label: "REM", color: "#6C7BF0" },
  { key: "awake", label: "Acordado", color: "var(--muted)" },
];

function SleepCard({ s }: { s: import("@/lib/api").SleepDetail }) {
  const stages = SLEEP_STAGES.map((st) => ({ ...st, v: s[st.key] })).filter((st) => st.v != null) as {
    key: string; label: string; color: string; v: number;
  }[];
  const total = stages.reduce((acc, st) => acc + st.v, 0);
  const sc = s.score != null ? sleepScore(s.score) : null;
  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Sono · última noite</span></div>
      <div className="sleep-top">
        <div className="sleep-total">{fmtSleep(s.hours)}<small>h</small></div>
        {sc && (
          <div className={`sleep-score ${sc.tone}`}>
            <b>{s.score}</b><span>/100 · {sc.label}</span>
          </div>
        )}
      </div>

      {stages.length >= 2 && total > 0 && (
        <>
          <div className="sleep-bar">
            {stages.map((st) => (
              <span key={st.key} style={{ width: `${(st.v / total) * 100}%`, background: st.color }} />
            ))}
          </div>
          <div className="sleep-legend">
            {stages.map((st) => (
              <div className="sleep-leg" key={st.key}>
                <span className="dot" style={{ background: st.color }} />
                <span className="lb">{st.label}</span>
                <span className="hv">{fmtHM(st.v)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {(s.respiration != null || s.spo2 != null) && (
        <p className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
          {s.respiration != null && <>Respiração {Math.round(s.respiration)} rpm</>}
          {s.respiration != null && s.spo2 != null && " · "}
          {s.spo2 != null && <>SpO₂ {s.spo2}%</>}
        </p>
      )}
    </section>
  );
}

export default function CorpoPage() {
  const router = useRouter();
  const [b, setB] = useState<BodyReading | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const data = await getBody();
      if (!data) { router.replace("/entrar"); return; }
      setB(data);
      setLoading(false);
    })();
  }, [router]);

  if (loading || !b) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const r = b.recovery;

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Leitura do corpo</div></div>
          <span style={{ width: 34 }} />
        </header>

        {!b.has_data || !r ? (
          <div className="card center">
            <p className="muted" style={{ margin: 0 }}>Ainda não temos dados de recuperação suficientes. Conecta o Garmin e usa o relógio à noite pra leitura do corpo. ⌚</p>
          </div>
        ) : (
          <>
            <div className={`state-card ${b.tone}`}>
              <div className="st">Estado do corpo 🩺</div>
              <h2>{b.state_label}</h2>
              {b.limiter_label && <p>Ponto de atenção principal: <b>{b.limiter_label}</b>.</p>}
              <p style={{ margin: "6px 0 0", fontWeight: 600 }}>{conduta(b.tone)}</p>
            </div>

            <section className="card">
              <div className="card-head"><span className="eyebrow">Recuperação</span></div>
              <div className="bgrid">
                {r.readiness_score != null && (
                  <div className="bmetric"><div className="k">Prontidão</div><div className="v">{r.readiness_score}<small>/100</small></div></div>
                )}
                {r.body_battery_wake != null && (
                  <div className="bmetric"><div className="k">Bateria ao acordar</div><div className="v">{r.body_battery_wake}</div></div>
                )}
                <div className="bmetric"><div className="k">Sono (média)</div><div className="v">{fmtSleep(r.sleep_avg_hours)}<small>h · {r.short_nights}/{r.nights_counted} curtas</small></div></div>
                <div className="bmetric"><div className="k">HRV</div><div className="v">{r.hrv_recent ?? "—"}{r.hrv_recent != null && <small>ms</small>}<Dir direction={r.hrv_direction} upIsGood={true} /></div></div>
                <div className="bmetric"><div className="k">FC repouso</div><div className="v">{r.rhr_recent ?? "—"}{r.rhr_recent != null && <small>bpm</small>}<Dir direction={r.rhr_direction} upIsGood={false} /></div></div>
                {r.stress_avg != null && (
                  <div className="bmetric"><div className="k">Estresse médio</div><div className="v">{r.stress_avg}</div></div>
                )}
                {r.respiration_sleep != null && (
                  <div className="bmetric"><div className="k">Respiração (sono)</div><div className="v">{Math.round(r.respiration_sleep)}<small>rpm</small></div></div>
                )}
              </div>
            </section>

            {b.sleep && b.sleep.hours != null && <SleepCard s={b.sleep} />}

            {b.trend && TREND_ROWS.some((row) => b.trend![row.key]) && (
              <section className="card">
                <div className="card-head"><span className="eyebrow">Últimos 7 dias</span></div>
                <div className="trend-list">
                  {TREND_ROWS.map((row) => {
                    const s = b.trend![row.key] as (number | null)[] | null;
                    if (!s) return null;
                    const lv = lastReal(s);
                    return (
                      <div className="trow" key={row.key}>
                        <span className="tl">{row.label}</span>
                        <Sparkline data={s} upIsGood={row.upIsGood} />
                        <span className="tv">{lv != null ? row.fmt(lv) : "—"}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
                  Verde = tendência boa, âmbar = de olho. O ponto é o dia mais recente.
                </p>
              </section>
            )}

            <section className="card">
              <div className="card-head"><span className="eyebrow">Carga de treino</span></div>
              <div className="prow">
                <span className="pl">ACWR (aguda ÷ crônica)</span>
                <span className="pv">{b.acwr ?? "—"} {b.acwr_status ? `· ${b.acwr_status}` : ""}</span>
              </div>
              <p className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
                Perto de 1,0 = carga equilibrada. Bem acima = risco de sobrecarga; bem abaixo = destreino.
              </p>
            </section>

            <p className="muted center" style={{ marginTop: 2 }}>Quer o papo completo? Fala com o coach 💬</p>
          </>
        )}
      </div>
    </main>
  );
}
