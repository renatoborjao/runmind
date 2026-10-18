"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getCalendar, type CalendarMonth, type WeekPlan } from "@/lib/api";
import WeekPlanSection from "./week-plan";

// UMA tela só: o calendário do mês em cima e, logo abaixo, o plano da semana com o
// detalhe de cada treino (o mesmo que o coach manda no chat). Tocar num dia do
// calendário seleciona a semana dele e leva até o treino daquele dia.

// Status por cor (não por tipo): verde = feito, amarelo = a realizar.
const DONE_COLOR = "var(--accent)";
const PLANNED_COLOR = "#F5A623";

const WEEKDAY_HEAD = ["D", "S", "T", "Q", "Q", "S", "S"];
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return isoOf(d);
}

// segunda-feira da semana de uma data (o plano é sempre de segunda a domingo)
function mondayOf(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return isoOf(d);
}

export default function TreinoPage() {
  const router = useRouter();
  const today = new Date();
  const [ym, setYm] = useState({ y: today.getFullYear(), m: today.getMonth() + 1 });
  const [cal, setCal] = useState<CalendarMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [authFail, setAuthFail] = useState(false);

  // semana selecionada (segunda, ISO). undefined = a do plano atual.
  const [weekStart, setWeekStart] = useState<string | undefined>(undefined);
  // a semana que o plano carregado cobre — pinta a faixa no calendário
  const [week, setWeek] = useState<{ start: string; end: string } | null>(null);
  // dia tocado no calendário: o plano rola até ele (tick refaz o scroll no mesmo dia)
  const [focus, setFocus] = useState<{ iso: string; tick: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    (async () => {
      const data = await getCalendar(ym.y, ym.m);
      if (!data) {
        setAuthFail(true);
        return;
      }
      setCal(data);
      setLoading(false);
    })();
  }, [ym]);

  useEffect(() => {
    if (authFail) router.replace("/entrar");
  }, [authFail, router]);

  const execByDate = useMemo(() => {
    const m = new Map<string, { kind: string }>();
    cal?.executed.forEach((e) => m.set(e.date_iso, { kind: e.kind }));
    return m;
  }, [cal]);

  const planByDate = useMemo(() => {
    const m = new Map<string, { kind: string; day_en: string }>();
    cal?.planned.forEach((p) => m.set(p.date_iso, { kind: p.kind, day_en: p.day_en }));
    return m;
  }, [cal]);

  function shift(delta: number) {
    setYm((c) => {
      const d = new Date(c.y, c.m - 1 + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() + 1 };
    });
  }

  // toque num dia: seleciona a semana dele (se for outra) e leva até o treino do dia
  function pickDay(iso: string) {
    setFocus({ iso, tick: Date.now() });
    if (!week || iso < week.start || iso > week.end) setWeekStart(mondayOf(iso));
  }

  // setas do plano: troca de semana e acompanha com o mês do calendário
  function goToWeek(startIso: string) {
    setFocus(null);
    setWeekStart(startIso);
    const mid = new Date(addDays(startIso, 3) + "T00:00:00");
    setYm({ y: mid.getFullYear(), m: mid.getMonth() + 1 });
  }

  function onLoaded(plan: WeekPlan, requested: string | undefined) {
    if (plan.has_plan && plan.week_start && plan.week_end) {
      setWeek({ start: plan.week_start, end: plan.week_end });
    } else if (requested) {
      setWeek({ start: requested, end: addDays(requested, 6) });
    }
  }

  const { y, m } = ym;
  const todayIso = isoOf(today);
  const firstWeekday = new Date(y, m - 1, 1).getDay();
  const daysInMonth = new Date(y, m, 0).getDate();
  const raceIso = cal?.race?.date_iso ?? null;

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  // lista do mês: executados + planejados, mais recentes primeiro
  const list = useMemo(() => {
    if (!cal) return [] as { iso: string; kind: string; title: string; sub: string; done: boolean; day_en?: string }[];
    const ex = cal.executed.map((e) => ({
      iso: e.date_iso, kind: e.kind, done: true, day_en: undefined as string | undefined,
      title: e.name.replace(/^.*(ritmind|runmind)\s*·?\s*/i, "").trim() || e.name,
      sub: `${e.km.toString().replace(".", ",")} km${e.pace ? ` · ${e.pace}/km` : ""}`,
    }));
    const pl = cal.planned.map((p) => ({
      iso: p.date_iso, kind: p.kind, done: false, day_en: p.day_en,
      title: p.workout_type, sub: "planejado",
    }));
    return [...ex, ...pl].sort((a, b) => b.iso.localeCompare(a.iso));
  }, [cal]);

  function openDay(iso: string, done: boolean, dayEn?: string) {
    // Treino FEITO abre a atividade RICA (mapa, parciais, análise do coach).
    // Full load (window.location) porque no PWA a query não chega no client-nav.
    if (done) window.location.assign(`/atividades?date=${iso}`);
    else if (dayEn) router.push(`/treino/detalhe?day=${dayEn}`);
  }

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>

        <div className="greet">
          <h1>Treinos</h1>
        </div>

        {cal?.race && (
          <section className="card">
            <div className="race">
              <div className="cd">
                <div className="n">{cal.race.days_until >= 0 ? cal.race.days_until : "—"}</div>
                <div className="l">{cal.race.days_until === 1 ? "dia" : "dias"}</div>
              </div>
              <div className="info">
                <div className="rn">🏁 {cal.race.name}</div>
                <div className="rd">{new Date(cal.race.date_iso + "T00:00:00").toLocaleDateString("pt-BR")}{cal.race.target_time ? ` · alvo ${cal.race.target_time}` : ""}</div>
              </div>
            </div>
          </section>
        )}

        {/* CALENDÁRIO do mês — toque num dia pra ver o plano daquela semana logo abaixo */}
        <section className="card">
          <div className="month-nav" style={{ marginBottom: 10 }}>
            <button className="icon-btn" aria-label="Mês anterior" onClick={() => shift(-1)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <span className="mlabel" style={{ textTransform: "capitalize" }}>{MONTHS[m - 1]} {y}</span>
            <button className="icon-btn" aria-label="Próximo mês" onClick={() => shift(1)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
            </button>
          </div>

          {loading ? (
            <p className="auth-sub center" style={{ margin: 0 }}>Carregando…</p>
          ) : (
            <>
              <div className="cal-head">{WEEKDAY_HEAD.map((h, i) => <span key={i}>{h}</span>)}</div>
              <div className="cal-grid">
                {cells.map((d, i) => {
                  if (d === null) return <div key={i} className="cal-cell empty" />;
                  const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
                  const ex = execByDate.get(iso);
                  const pl = planByDate.get(iso);
                  const isToday = iso === todayIso;
                  const isRace = iso === raceIso;
                  const inWeek = !!week && iso >= week.start && iso <= week.end;
                  return (
                    <div
                      key={i}
                      className={`cal-cell${ex || pl ? " has" : ""}${isToday ? " today" : ""}${inWeek ? " inweek" : ""}${focus?.iso === iso ? " sel" : ""}`}
                      onClick={() => pickDay(iso)}
                    >
                      {isRace && <span className="flag">🏁</span>}
                      {ex ? (
                        <span className="daynum" style={{ background: DONE_COLOR }}>{d}</span>
                      ) : pl ? (
                        <span className="daynum" style={{ background: PLANNED_COLOR }}>{d}</span>
                      ) : (
                        <span>{d}</span>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="legend">
                <span><i style={{ background: DONE_COLOR, borderRadius: "50%", width: 12, height: 12 }} />Feito</span>
                <span><i style={{ background: PLANNED_COLOR, borderRadius: "50%", width: 12, height: 12 }} />A realizar</span>
                <span><i style={{ background: "var(--accent-wash)", borderRadius: 4, width: 12, height: 12, border: "1px solid var(--accent)" }} />Semana aberta abaixo</span>
              </div>
            </>
          )}
        </section>

        {/* PLANO DA SEMANA — o detalhe de cada treino, aberto */}
        <WeekPlanSection
          weekStart={weekStart}
          focusIso={focus?.iso ?? null}
          focusTick={focus?.tick ?? 0}
          onLoaded={onLoaded}
          onNavigate={goToWeek}
        />

        {/* histórico do mês */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Treinos do mês</span></div>
          {list.length > 0 ? (
            list.map((it, i) => (
              <div key={i} className="wrow" onClick={() => openDay(it.iso, it.done, it.day_en)}>
                <div className="date">
                  <div className="dn">{new Date(it.iso + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "")}</div>
                  <div className="dd">{Number(it.iso.slice(-2))}</div>
                </div>
                <span className="kdot" style={{ background: it.done ? DONE_COLOR : PLANNED_COLOR }} />
                <div className="info">
                  <div className="wt">{it.title}</div>
                  <div className="wd">{it.sub}</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
              </div>
            ))
          ) : (
            <p className="muted" style={{ margin: 0 }}>Sem treinos neste mês.</p>
          )}
        </section>

      </div>
      <BottomNav />
    </main>
  );
}
