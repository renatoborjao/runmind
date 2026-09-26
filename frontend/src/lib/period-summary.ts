// Resumo SEMANAL (seg–dom) e MENSAL das corridas do atleta, calculado do feed
// (a mesma lista de atividades da tela de atividades, já sem duplicata
// Garmin×Strava). Datas pela data LOCAL da corrida (date_iso) — a semana vira
// na segunda, igual ao plano.

import type { FeedItem } from "./api";

export type PeriodKind = "week" | "month";

export interface PeriodSummary {
  kind: PeriodKind;
  offset: number;          // 0 = período atual, -1 = anterior…
  isCurrent: boolean;
  title: string;           // "Resumo da semana" / "Resumo do mês"
  label: string;           // "22 a 28 de setembro" / "Setembro 2026"
  km: number;
  runs: number;
  seconds: number;
  paceSec: number | null;  // tempo total / km total
  longestKm: number;
  // barras do gráfico — semana: 1 por DIA (S T Q…); mês: 1 por SEMANA
  // (seg–dom recortada no mês, rótulo "7–13"). 30 barras diárias no mês não
  // diziam nada; por semana mostra como o mês evoluiu.
  // label = rótulo principal ("Seg" / "Sem 2"); sub = datas da semana no mês
  bars: { label: string; sub?: string; km: number; future: boolean }[];
  // variação de km vs o período anterior — no período ATUAL (incompleto)
  // compara com o mesmo trecho do anterior (seg–qua × seg–qua), senão mente.
  deltaPct: number | null;
  vsLabel: string;         // "vs semana passada" / "vs mês passado"
}

const WEEKDAY = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const MONTHS = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function shortMonth(m: number): string {
  return MONTHS[m].slice(0, 3);
}

// [início, fim] inclusivos do período `offset` a partir de hoje
function bounds(kind: PeriodKind, offset: number, today: Date): [Date, Date] {
  const t = startOfDay(today);
  if (kind === "week") {
    const monday = addDays(t, -((t.getDay() + 6) % 7) + offset * 7);
    return [monday, addDays(monday, 6)];
  }
  const first = new Date(t.getFullYear(), t.getMonth() + offset, 1);
  return [first, new Date(first.getFullYear(), first.getMonth() + 1, 0)];
}

function kmByDay(feed: FeedItem[]): Map<string, { km: number; s: number; n: number; max: number }> {
  const m = new Map<string, { km: number; s: number; n: number; max: number }>();
  for (const it of feed) {
    const k = (it.date_iso || "").slice(0, 10);
    if (!k || !(it.distance_km > 0)) continue;
    const cur = m.get(k) ?? { km: 0, s: 0, n: 0, max: 0 };
    cur.km += it.distance_km;
    cur.s += it.duration_s || (it.duration_min || 0) * 60;
    cur.n += 1;
    cur.max = Math.max(cur.max, it.distance_km);
    m.set(k, cur);
  }
  return m;
}

function sumKm(byDay: Map<string, { km: number }>, from: Date, to: Date): number {
  let total = 0;
  for (let d = from; d <= to; d = addDays(d, 1)) total += byDay.get(isoOf(d))?.km ?? 0;
  return total;
}

export function periodSummary(
  feed: FeedItem[], kind: PeriodKind, offset: number, today: Date = new Date(),
): PeriodSummary {
  const byDay = kmByDay(feed);
  const [start, end] = bounds(kind, offset, today);
  const t = startOfDay(today);
  const isCurrent = offset === 0;

  let km = 0, seconds = 0, runs = 0, longestKm = 0;
  const bars: PeriodSummary["bars"] = [];
  let bucket: PeriodSummary["bars"][number] | null = null;
  let bucketFrom = 0;
  for (let d = start; d <= end; d = addDays(d, 1)) {
    const v = byDay.get(isoOf(d));
    if (v) { km += v.km; seconds += v.s; runs += v.n; longestKm = Math.max(longestKm, v.max); }
    if (kind === "week") {
      bars.push({ label: WEEKDAY[(d.getDay() + 6) % 7], km: v?.km ?? 0, future: d > t });
      continue;
    }
    // mês: nova barra a cada segunda (ou no dia 1)
    if (!bucket || d.getDay() === 1) {
      bucket = { label: `Sem ${bars.length + 1}`, km: 0, future: d > t };
      bucketFrom = d.getDate();
      bars.push(bucket);
    }
    bucket.km += v?.km ?? 0;
    bucket.sub = bucketFrom === d.getDate() ? String(bucketFrom) : `${bucketFrom}–${d.getDate()}`;
  }

  // anterior: período cheio; se o atual está em andamento, só o mesmo trecho
  const [pStart, pEnd] = bounds(kind, offset - 1, today);
  let prevTo = pEnd;
  if (isCurrent) {
    const elapsed = Math.round((t.getTime() - start.getTime()) / 86400000);
    const cut = addDays(pStart, elapsed);
    prevTo = cut < pEnd ? cut : pEnd;
  }
  const prevKm = sumKm(byDay, pStart, prevTo);
  const deltaPct = prevKm > 0 ? Math.round(((km - prevKm) / prevKm) * 100) : null;

  const label = kind === "week"
    ? (start.getMonth() === end.getMonth()
      ? `${start.getDate()} a ${end.getDate()} de ${MONTHS[end.getMonth()]}`
      : `${start.getDate()} ${shortMonth(start.getMonth())} a ${end.getDate()} ${shortMonth(end.getMonth())}`)
    : `${MONTHS[start.getMonth()][0].toUpperCase()}${MONTHS[start.getMonth()].slice(1)} ${start.getFullYear()}`;

  return {
    kind, offset, isCurrent,
    title: kind === "week" ? "Resumo da semana" : "Resumo do mês",
    label,
    km, runs, seconds,
    paceSec: km > 0 && seconds > 0 ? seconds / km : null,
    longestKm,
    bars,
    deltaPct,
    vsLabel: kind === "week" ? "vs semana passada" : "vs mês passado",
  };
}

export function fmtPace(sec: number | null): string {
  if (sec == null) return "—";
  const total = Math.round(sec);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function fmtKm(v: number, decimals = 1): string {
  return v.toFixed(decimals).replace(".", ",");
}
