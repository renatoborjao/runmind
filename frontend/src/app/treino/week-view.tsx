"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getWeekPlan, type WeekPlan, type WeekPlanDay, type WorkoutStep } from "@/lib/api";

// A visão do PLANO DA SEMANA — o mesmo que o coach manda no chat (objetivo, bloco,
// fase, treino a treino), só que na tela: dá pra ver a semana inteira de uma vez,
// o que já foi feito ao lado de cada dia e as semanas anteriores.

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

function DayRow({
  d, open, onToggle, isCurrentWeek,
}: { d: WeekPlanDay; open: boolean; onToggle: () => void; isCurrentWeek: boolean }) {
  const router = useRouter();
  const s = d.session;
  const ex = d.executed;

  if (!s && !ex) {
    return (
      <div className="wk-day rest">
        <div className="date"><div className="dn">{d.day_pt}</div><div className="dd">{d.date_num}</div></div>
        <span className="muted" style={{ margin: 0 }}>Descanso</span>
      </div>
    );
  }

  const title = s
    ? `${s.workout_type}${s.distance_km ? ` · ${kmText(s.distance_km)}` : s.duration_min ? ` · ${s.duration_min} min` : ""}`
    : "Treino extra";

  const pace = s ? paceText(s.pace_min, s.pace_max) : null;

  const sub =
    d.status === "done" && ex
      ? `${kmText(ex.km)}${ex.pace ? ` · ${ex.pace}/km` : ""}${s && s.distance_km ? ` (plano ${kmText(s.distance_km)})` : ""}`
      : pace ?? "";

  const hasMore = !!s && (s.purpose || s.structure || s.notes || s.steps.length > 0 || s.adjusted || d.status === "done");

  return (
    <div className={`wk-day${d.is_today ? " today" : ""}${open ? " open" : ""}`}>
      <div className="wk-row" onClick={hasMore ? onToggle : undefined} role={hasMore ? "button" : undefined}>
        <div className="date"><div className="dn">{d.day_pt}</div><div className="dd">{d.date_num}</div></div>
        <span className="kdot" style={{ background: dotColor(d.status) }} />
        <div className="info">
          <div className="wt">
            {title}
            {s?.is_oneoff && <span className="wk-tag">avulso</span>}
          </div>
          {sub && <div className="wd">{sub}</div>}
        </div>
        <span className={`wk-status ${d.status}`}>{STATUS_TAG[d.status]}</span>
        {hasMore && (
          <svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
        )}
      </div>

      {open && s && (
        <div className="wk-more">
          {s.purpose && <p><b>Foco:</b> {s.purpose}</p>}
          {s.objective && s.objective !== s.purpose && <p>{s.objective}</p>}
          {(s.structure || s.notes) && (
            <p className="muted" style={{ margin: "0 0 8px" }}>{s.structure || s.notes}</p>
          )}
          {s.adjusted && (
            <p className="wk-adj">Ajustado{s.adjustment_reason ? `: ${s.adjustment_reason}` : ""}</p>
          )}
          {s.steps.length > 0 && (
            <div className="wk-steps">
              <StepRows steps={s.steps} />
            </div>
          )}
          {d.status === "done" && ex && (
            <p className="wk-did">
              Você fez {kmText(ex.km)} em {ex.duration_min} min{ex.pace ? ` (${ex.pace}/km)` : ""}.
            </p>
          )}
          <div className="wk-actions">
            {d.status === "done" ? (
              <button className="btn-sm" onClick={() => window.location.assign(`/atividades?date=${d.date_iso}`)}>
                Ver como foi
              </button>
            ) : isCurrentWeek && !d.is_past ? (
              <button className="btn-sm" onClick={() => router.push(`/treino/detalhe?day=${d.day_en}`)}>
                Abrir treino
              </button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

export default function WeekView() {
  const router = useRouter();
  const [weekStart, setWeekStart] = useState<string | undefined>(undefined);
  const [data, setData] = useState<WeekPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [authFail, setAuthFail] = useState(false);
  const [openDay, setOpenDay] = useState<string | null>(null);

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
      setData(res);
      setLoading(false);
      // abre o treino de HOJE (ou nenhum, numa semana passada/futura)
      const today = res.days?.find((x) => x.is_today && x.session);
      setOpenDay(today ? today.date_iso : null);
    })();
    return () => { alive = false; };
  }, [weekStart]);

  useEffect(() => {
    if (authFail) router.replace("/entrar");
  }, [authFail, router]);

  if (loading && !data) {
    return <section className="card"><p className="auth-sub center" style={{ margin: 0 }}>Carregando…</p></section>;
  }

  if (!data || !data.has_plan || !data.days) {
    return (
      <section className="card">
        <div className="card-head"><span className="eyebrow">Plano da semana</span></div>
        <p className="muted" style={{ margin: 0 }}>
          Ainda não há um plano para esta semana. Assim que o coach montar, ele aparece aqui.
        </p>
      </section>
    );
  }

  const t = data.totals;
  const pct = t && t.planned_km > 0 ? Math.min(100, Math.round((t.done_km / t.planned_km) * 100)) : 0;
  const label = data.week_start && data.week_end ? rangeLabel(data.week_start, data.week_end) : "";

  return (
    <>
      {data.race && (
        <section className="card">
          <div className="race">
            <div className="cd">
              <div className="n">{data.race.days_until >= 0 ? data.race.days_until : "—"}</div>
              <div className="l">{data.race.days_until === 1 ? "dia" : "dias"}</div>
            </div>
            <div className="info">
              <div className="rn">🏁 {data.race.name}</div>
              <div className="rd">{new Date(data.race.date_iso + "T00:00:00").toLocaleDateString("pt-BR")}{data.race.target_time ? ` · alvo ${data.race.target_time}` : ""}</div>
            </div>
          </div>
        </section>
      )}

      <section className="card wk-head" style={{ opacity: loading ? 0.6 : 1 }}>
        <div className="month-nav" style={{ marginBottom: 10 }}>
          <button className="icon-btn" aria-label="Semana anterior" disabled={!data.prev_week_start}
            style={{ opacity: data.prev_week_start ? 1 : 0.3 }}
            onClick={() => data.prev_week_start && setWeekStart(data.prev_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <span className="mlabel">
            {label}
            <small className="wk-when">{data.is_current ? "semana do plano" : "semana anterior"}</small>
          </span>
          <button className="icon-btn" aria-label="Próxima semana" disabled={!data.next_week_start}
            style={{ opacity: data.next_week_start ? 1 : 0.3 }}
            onClick={() => data.next_week_start && setWeekStart(data.next_week_start)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>

        <div className="wk-chips">
          {data.phase_label && <span className="badge"><span className="dot" />{data.phase_label}</span>}
          {data.is_deload && <span className="wk-tag warn">semana de recuperação</span>}
        </div>

        {data.block_label && <p className="wk-block">📦 {data.block_label}</p>}
        {data.objective && <p className="wk-obj">🎯 {data.objective}</p>}

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

      <section className="card">
        <div className="card-head"><span className="eyebrow">Treino a treino</span></div>
        {data.days.map((d) => (
          <DayRow
            key={d.date_iso}
            d={d}
            open={openDay === d.date_iso}
            onToggle={() => setOpenDay(openDay === d.date_iso ? null : d.date_iso)}
            isCurrentWeek={!!data.is_current}
          />
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
