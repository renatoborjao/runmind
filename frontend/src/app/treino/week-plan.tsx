"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getWeekPlan,
  type RaceMapData,
  type WeekPlan,
  type WeekPlanDay,
  type WorkoutStep,
} from "@/lib/api";

// O PLANO DA SEMANA — o mesmo que o coach manda no chat (objetivo, bloco, fase e o
// DETALHE de cada treino, passo a passo), só que na tela, junto do calendário: a
// semana inteira aberta de uma vez, com o que já foi feito ao lado de cada dia.

const DONE = "var(--accent)";
const PLANNED = "#F5A623";
const MUTED = "var(--muted)";

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const STEP_PT: Record<string, string> = {
  warmup: "Aquecimento",
  cooldown: "Desaquecimento",
  run: "Corrida",
  interval: "Tiro forte",
  recovery: "Recuperação",
  rest: "Pausa",
  repeat: "Repetir",
};

const STATUS_TAG: Record<string, string> = {
  done: "feito",
  today: "hoje",
  upcoming: "a fazer",
  missed: "não realizado",
};

function kmText(km: number): string {
  return `${String(km).replace(".", ",")} km`;
}

function rangeLabel(startIso: string, endIso: string): string {
  const s = new Date(startIso + "T00:00:00");
  const e = new Date(endIso + "T00:00:00");
  if (s.getMonth() === e.getMonth()) return `${s.getDate()}–${e.getDate()} ${MONTHS[e.getMonth()]}`;
  return `${s.getDate()} ${MONTHS[s.getMonth()]} – ${e.getDate()} ${MONTHS[e.getMonth()]}`;
}

function paceText(min: string | null, max: string | null): string | null {
  if (min && max) return `${min}–${max}/km`;
  if (min) return `${min}/km`;
  return null;
}

function stepAmount(s: WorkoutStep): string {
  if (s.distance_m != null)
    return s.distance_m >= 1000 ? kmText(s.distance_m / 1000) : `${s.distance_m} m`;
  if (s.duration_sec != null)
    return s.duration_sec >= 60 ? `${Math.round(s.duration_sec / 60)} min` : `${s.duration_sec}s`;
  return "livre";
}

function StepRows({ steps, depth = 0 }: { steps: WorkoutStep[]; depth?: number }) {
  return (
    <>
      {steps.map((s, i) =>
        s.kind === "repeat" && s.steps?.length ? (
          <div key={i} style={{ marginLeft: depth * 10 }}>
            <div className="wk-step rep">{s.reps ?? "?"}× repetir</div>
            <StepRows steps={s.steps} depth={depth + 1} />
          </div>
        ) : (
          <div key={i} className="wk-step" style={{ marginLeft: depth * 10 }}>
            <span className="t">{STEP_PT[s.kind] ?? s.kind}</span>
            <span className="d">{stepAmount(s)}</span>
            <span className="p">{paceText(s.pace_min, s.pace_max)?.replace("/km", "") ?? "leve"}</span>
          </div>
        ),
      )}
    </>
  );
}

function dotColor(status: string): string {
  if (status === "done") return DONE;
  if (status === "missed") return MUTED;
  return PLANNED;
}

function DayCard({ d, focused, isCurrentWeek }: { d: WeekPlanDay; focused: boolean; isCurrentWeek: boolean }) {
  const router = useRouter();
  const s = d.session;
  const ex = d.executed;

  if (!s && !ex) {
    return (
      <div id={`wk-${d.date_iso}`} className={`wk-day rest${focused ? " focus" : ""}`}>
        <div className="date"><div className="dn">{d.day_pt}</div><div className="dd">{d.date_num}</div></div>
        <span className="muted" style={{ margin: 0 }}>Descanso</span>
      </div>
    );
  }

  const title = s
    ? `${s.workout_type}${s.distance_km ? ` · ${kmText(s.distance_km)}` : s.duration_min ? ` · ${s.duration_min} min` : ""}`
    : "Treino extra";

  const pace = s ? paceText(s.pace_min, s.pace_max) : null;

  return (
    <div id={`wk-${d.date_iso}`} className={`wk-day${d.is_today ? " today" : ""}${focused ? " focus" : ""}`}>
      <div className="wk-main">
        <div className="date"><div className="dn">{d.day_pt}</div><div className="dd">{d.date_num}</div></div>
        <span className="kdot" style={{ background: dotColor(d.status) }} />
        <div className="wk-body">
          <div className="wk-titlerow">
            <div className="wt">
              {title}
              {s?.is_oneoff && <span className="wk-tag">avulso</span>}
            </div>
            <span className={`wk-status ${d.status}`}>{STATUS_TAG[d.status]}</span>
          </div>
          {pace && <div className="wd">Ritmo-alvo {pace}</div>}

          {s && s.detail.length > 0 && (
            <ul className="wk-detail">
              {s.detail.map((line, i) => <li key={i}>{line}</li>)}
            </ul>
          )}

          {/* sem a prosa do coach (plano externo, sessão antiga): os passos estruturados */}
          {s && s.detail.length === 0 && s.steps.length > 0 && (
            <div className="wk-steps"><StepRows steps={s.steps} /></div>
          )}
          {s && s.detail.length === 0 && s.steps.length === 0 && (s.structure || s.notes) && (
            <p className="muted" style={{ margin: "6px 0" }}>{s.structure || s.notes}</p>
          )}

          {s?.shoe && <div className="wk-shoe">{s.shoe}</div>}
          {s?.adjusted && <div className="wk-adj">⚠️ {s.adjustment_reason || "Treino ajustado pelo coach"}</div>}

          {d.status === "done" && ex && (
            <p className="wk-did">
              Você fez {kmText(ex.km)} em {ex.duration_min} min{ex.pace ? ` (${ex.pace}/km)` : ""}.
            </p>
          )}

          {(d.status === "done" || (isCurrentWeek && !d.is_past && s)) && (
            <div className="wk-actions">
              {d.status === "done" ? (
                <button className="btn-sm" onClick={() => window.location.assign(`/atividades?date=${d.date_iso}`)}>
                  Ver como foi
                </button>
              ) : (
                <button className="btn-sm" onClick={() => router.push(`/treino/detalhe?day=${d.day_en}`)}>
                  Abrir treino
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function dayMonth(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// O MAPA ATÉ A PROVA — o olhar pra frente: quantas semanas faltam e como o ciclo costuma
// se organizar até o dia. Calculado na hora e sempre "previsto" (o coach ajusta se o corpo
// pedir); só fases e marcos, sem números de volume.
function RaceMapCard({ map }: { map: RaceMapData }) {
  return (
    <section className="card rmap">
      <div className="card-head"><span className="eyebrow">Mapa até a prova</span></div>
      <p className="rmap-head">
        <b>{map.weeks_left === 1 ? "Semana da prova" : `Faltam ${map.weeks_left} semanas`}</b>
        {" · "}{map.target}{" · "}{dayMonth(map.race_date)}
      </p>
      <ol className="rmap-list">
        {map.segments.map((s) => (
          <li key={`${s.key}-${s.start}`} className={`rmap-row${s.current ? " on" : ""}`}>
            <i className="rmap-dot" aria-hidden />
            <span className="rmap-name">
              {(s.key === "mini_polimento" || s.key === "polimento") && "🏁 "}
              {s.label}
              {s.current && <small className="wk-tag">agora</small>}
            </span>
            <span className="rmap-when">{rangeLabel(s.start, s.end)} · {s.weeks} sem</span>
          </li>
        ))}
      </ol>
      {map.markers.map((m) => (
        <p key={m.date_iso + m.label} className="rmap-marker">
          🏁 {m.label}{m.role ? ` (${m.role})` : ""} · {dayMonth(m.date_iso)}
          {m.note ? ` — ${m.note}` : ""}
        </p>
      ))}
      <p className="rmap-note">{map.note}</p>
    </section>
  );
}

export default function WeekPlanSection({
  weekStart, focusIso, focusTick, onLoaded, onNavigate,
}: {
  weekStart: string | undefined;
  focusIso: string | null;
  focusTick: number;
  onLoaded: (plan: WeekPlan, requested: string | undefined) => void;
  onNavigate: (weekStartIso: string) => void;
}) {
  const router = useRouter();
  const [data, setData] = useState<WeekPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [authFail, setAuthFail] = useState(false);
  const loadedFor = useRef<string | undefined | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    (async () => {
      const res = await getWeekPlan(weekStart);
      if (!alive) return;
      if (!res) {
        setAuthFail(true);
        return;
      }
      loadedFor.current = weekStart;
      setData(res);
      setLoading(false);
      onLoaded(res, weekStart);
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekStart]);

  useEffect(() => {
    if (authFail) router.replace("/entrar");
  }, [authFail, router]);

  // toque num dia do calendário: leva até o treino daquele dia
  useEffect(() => {
    if (!focusIso || loading) return;
    const el = document.getElementById(`wk-${focusIso}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusIso, focusTick, loading, data]);

  if (loading && !data) {
    return <section className="card"><p className="auth-sub center" style={{ margin: 0 }}>Carregando o plano…</p></section>;
  }

  if (!data || !data.has_plan || !data.days) {
    return (
      <section className="card" style={{ opacity: loading ? 0.6 : 1 }}>
        <div className="card-head"><span className="eyebrow">Plano da semana</span></div>
        <div className="month-nav" style={{ marginBottom: 10 }}>
          <button className="icon-btn" aria-label="Semana anterior" disabled={!data?.prev_week_start}
            style={{ opacity: data?.prev_week_start ? 1 : 0.3 }}
            onClick={() => data?.prev_week_start && onNavigate(data.prev_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <span className="muted" style={{ margin: 0 }}>Sem plano para esta semana</span>
          <button className="icon-btn" aria-label="Próxima semana" disabled={!data?.next_week_start}
            style={{ opacity: data?.next_week_start ? 1 : 0.3 }}
            onClick={() => data?.next_week_start && onNavigate(data.next_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          O coach monta o plano de cada semana no domingo — assim que existir, ele aparece aqui.
        </p>
      </section>
    );
  }

  const t = data.totals;
  const pct = t && t.planned_km > 0 ? Math.min(100, Math.round((t.done_km / t.planned_km) * 100)) : 0;
  const label = data.week_start && data.week_end ? rangeLabel(data.week_start, data.week_end) : "";

  return (
    <>
      <section className="card wk-head" style={{ opacity: loading ? 0.6 : 1 }}>
        <div className="card-head"><span className="eyebrow">Plano da semana</span></div>
        <div className="month-nav" style={{ marginBottom: 10 }}>
          <button className="icon-btn" aria-label="Semana anterior" disabled={!data.prev_week_start}
            style={{ opacity: data.prev_week_start ? 1 : 0.3 }}
            onClick={() => data.prev_week_start && onNavigate(data.prev_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <span className="mlabel">
            {label}
            <small className="wk-when">{data.is_current ? "semana do plano" : "semana anterior"}</small>
          </span>
          <button className="icon-btn" aria-label="Próxima semana" disabled={!data.next_week_start}
            style={{ opacity: data.next_week_start ? 1 : 0.3 }}
            onClick={() => data.next_week_start && onNavigate(data.next_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>

        <div className="wk-chips">
          {data.phase_label && <span className="badge"><span className="dot" />{data.phase_label}</span>}
          {data.is_deload && <span className="wk-tag warn">semana mais leve</span>}
        </div>

        {data.block_label && <p className="wk-block">📦 {data.block_label}</p>}
        {data.objective && <p className="wk-obj">🎯 {data.objective}</p>}
        {data.is_deload && data.deload_why && <p className="wk-note">🔽 {data.deload_why}</p>}

        {t && t.sessions > 0 && (
          <div className="wk-progress">
            <div className="wk-bar" aria-hidden><i style={{ width: `${pct}%` }} /></div>
            <div className="wk-count">
              <b>{String(t.done_km).replace(".", ",")}</b> de {String(t.planned_km).replace(".", ",")} km
              {" · "}
              <b>{t.done_sessions}</b> de {t.sessions} treinos
            </div>
          </div>
        )}

        {data.extra_day_note && (
          <p className="wk-note">💡 {data.extra_day_note} Se topar, fala com o coach na aba Coach que eu incluo no plano.</p>
        )}
      </section>

      {data.race_map && <RaceMapCard map={data.race_map} />}

      <section className="card" style={{ opacity: loading ? 0.6 : 1 }}>
        <div className="card-head"><span className="eyebrow">Treino a treino</span></div>
        {data.days.map((d) => (
          <DayCard key={d.date_iso} d={d} focused={focusIso === d.date_iso} isCurrentWeek={!!data.is_current} />
        ))}
        <div className="legend">
          <span><i style={{ background: DONE }} />Feito</span>
          <span><i style={{ background: PLANNED }} />A fazer</span>
          <span><i style={{ background: MUTED }} />Não realizado</span>
        </div>
      </section>
    </>
  );
}
