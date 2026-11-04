// Cards de compartilhar inspirados nos stories de corrida que o pessoal posta:
//  - "Treino com voltas": painel escuro com os números, a ESTRUTURA do treino
//    (aquecimento, séries, recuperação...) e a tabela de VOLTAS do relógio, com
//    as mais rápidas na cor da marca. Usa as voltas REAIS do Garmin (share-context).
//  - "Minimalista": números empilhados e centralizados em branco, com o
//    percurso rabiscado na cor da marca por cima (como se fosse feito à mão).
// Tudo determinístico (sem IA). Cada modelo funciona nas duas versões —
// Transparente e Card — e o canvas é justo ao conteúdo no Transparente.

import type { FeedItem, ShareLap } from "./api";
import type { RunExtras } from "./run-card-extras";
import {
  CANVAS_FONT, applySoftShadow, drawBrand, fitText, fmtDur, outlinedText, roundRect, withShadow,
} from "./share-canvas";

const ORANGE = "#1FD9B8"; // teal da marca Ritmind
const PANEL = "rgba(10,11,16,0.9)";
const MUTED_PANEL = "rgba(255,255,255,0.62)";
const MUTED_BARE = "rgba(255,255,255,0.9)";
const MUTED = MUTED_PANEL;

const CARD_MIN_H = 1350;

function km2(v: number): string { return v.toFixed(2).replace(".", ","); }
function durOf(it: FeedItem): number { return it.duration_s || (it.duration_min || 0) * 60; }

function paceSecOf(p: string | null | undefined): number | null {
  if (!p) return null;
  const m = /(\d+):(\d{2})/.exec(p);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}
function fmtPace(sec: number | null): string {
  if (sec == null || !isFinite(sec)) return "—";
  const t = Math.round(sec);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}
// tempo de volta: "20s" abaixo de 1 min, senão "1:30" (ou "1:02:10")
function fmtLapTime(s: number): string {
  const t = Math.round(s);
  if (t < 60) return `${t}s`;
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
    : `${m}:${String(sec).padStart(2, "0")}`;
}
function lapKm(l: ShareLap): string { return km2(l.distance_m / 1000); }
// pace da volta calculado (tempo ÷ distância) — a string do relógio vinha errada
function lapPaceSec(l: ShareLap): number | null {
  return l.distance_m > 0 && l.duration_s > 0 ? l.duration_s / (l.distance_m / 1000) : null;
}
// pace médio de um conjunto de voltas (tempo total ÷ distância total)
function groupPace(laps: ShareLap[]): number | null {
  const d = laps.reduce((a, l) => a + l.distance_m, 0);
  const s = laps.reduce((a, l) => a + l.duration_s, 0);
  return d > 0 ? s / (d / 1000) : null;
}

// ---------------------------------------------------------------------------
// Estrutura do treino a partir das voltas do relógio (pura — fácil de conferir)
// ---------------------------------------------------------------------------

export interface LapGroup { name: string; detail: string; }
export interface LapRow { n: number; lap: ShareLap; fast: boolean; }
export interface LapStructure { unit: "Bloco" | "Km"; title: string; groups: LapGroup[]; rows: LapRow[]; hidden: number; }

const MAX_ROWS = 22;

export function lapStructure(laps: ShareLap[], workoutName?: string | null): LapStructure {
  // sem esforço/recuperação (corrida contínua): uma estrutura só + as voltas por km
  if (!laps.some((l) => l.kind !== "other")) {
    const total = laps.reduce((a, l) => a + l.distance_m, 0) / 1000;
    let rows: LapRow[] = laps.map((lap, i) => ({ n: i + 1, lap, fast: false }));
    const hidden = Math.max(0, rows.length - MAX_ROWS);
    if (hidden) rows = rows.slice(0, MAX_ROWS);
    const ranked = rows.filter((r) => lapPaceSec(r.lap) != null)
      .sort((a, b) => lapPaceSec(a.lap)! - lapPaceSec(b.lap)!);
    if (ranked.length >= 3) ranked.slice(0, Math.max(1, Math.floor(ranked.length / 3))).forEach((r) => { r.fast = true; });
    return {
      unit: "Km",
      title: (workoutName || "").trim().toUpperCase() || "TREINO COM PARCIAIS",
      groups: [{ name: "Corrida contínua", detail: `${km2(total)} km · ${fmtPace(groupPace(laps))}/km` }],
      rows, hidden,
    };
  }
  const first = laps.findIndex((l) => l.kind !== "other");
  let last = -1;
  laps.forEach((l, i) => { if (l.kind !== "other") last = i; });
  const lead = first > 0 ? laps.slice(0, first) : [];
  const trail = last >= 0 && last < laps.length - 1 ? laps.slice(last + 1) : [];
  const midStart = first > 0 ? first : 0;
  const midEnd = last >= 0 ? last + 1 : laps.length;
  const middle = laps.slice(midStart, midEnd);

  const dist = (ls: ShareLap[]) => `${km2(ls.reduce((a, l) => a + l.distance_m, 0) / 1000)} km`;
  const groups: LapGroup[] = [];
  if (lead.length) groups.push({ name: "Aquecimento", detail: `${dist(lead)} · ${fmtPace(groupPace(lead))}/km` });

  // o miolo em trechos: contínuo ("other") × intervalado (esforço/recuperação)
  const runs: { interval: boolean; laps: ShareLap[] }[] = [];
  for (const l of middle) {
    const interval = l.kind !== "other";
    const cur = runs[runs.length - 1];
    if (cur && cur.interval === interval) cur.laps.push(l); else runs.push({ interval, laps: [l] });
  }
  const contCount = runs.filter((r) => !r.interval).length;
  let cont = 0;
  for (const r of runs) {
    if (!r.interval) {
      cont += 1;
      groups.push({
        name: contCount > 1 ? `Bloco ${cont}` : "Ritmo sustentado",
        detail: `${dist(r.laps)} · ${fmtPace(groupPace(r.laps))}/km`,
      });
      continue;
    }
    const eff = r.laps.filter((l) => l.kind === "effort");
    const rec = r.laps.filter((l) => l.kind === "recovery");
    if (eff.length) {
      groups.push({
        name: eff.length > 1 ? `Séries (${eff.length}×)` : "Esforço",
        detail: `${eff.length}× ${dist(eff.slice(0, 1))} · ${fmtPace(groupPace(eff))}/km`,
      });
    }
    if (rec.length) groups.push({ name: "Recuperação", detail: `${rec.length}× ${dist(rec.slice(0, 1))} · ${fmtPace(groupPace(rec))}/km` });
  }
  if (trail.length) groups.push({ name: "Desaquecimento", detail: `${dist(trail)} · ${fmtPace(groupPace(trail))}/km` });

  // tabela: as voltas do miolo, numeradas como no relógio
  let rows: LapRow[] = laps.map((lap, i) => ({ n: i + 1, lap, fast: false }));
  const hidden = Math.max(0, rows.length - MAX_ROWS);
  if (hidden) rows = rows.slice(0, MAX_ROWS);
  // destaque: o terço mais rápido dos esforços (precisa de 3+ pra comparar)
  const eff = rows.filter((r) => r.lap.kind === "effort" && lapPaceSec(r.lap) != null);
  if (eff.length >= 3) {
    const sorted = [...eff].sort((a, b) => lapPaceSec(a.lap)! - lapPaceSec(b.lap)!);
    sorted.slice(0, Math.max(1, Math.floor(eff.length / 3))).forEach((r) => { r.fast = true; });
  }

  const hasSeries = middle.filter((l) => l.kind === "effort").length > 1;
  const named = (workoutName || "").trim().toUpperCase();
  const title = named || (hasSeries ? "TREINO DE SÉRIES" : "TREINO COM BLOCOS");
  return { unit: "Bloco", title, groups, rows, hidden };
}

// ---------------------------------------------------------------------------
// TREINO COM VOLTAS
// ---------------------------------------------------------------------------

const PANEL_W = 660;
const PAD = 38;
const METRIC_ROW = 92;
const GROUP_ROW = 58;
const LAP_ROW = 46;

function metricCells(it: FeedItem, x: RunExtras): [string, string][] {
  const c: [string, string][] = [
    ["Distância", `${km2(it.distance_km)} km`],
    ["Tempo", fmtDur(durOf(it))],
    ["Ritmo", `${it.pace ?? "—"} /km`],
  ];
  if (it.avg_hr != null) c.push(["FC média", `${it.avg_hr} bpm`]);
  if (x.cal) c.push(["Calorias", `${x.cal} kcal`]);
  if (it.elevation_gain != null) c.push(["Elevação", `${Math.round(it.elevation_gain)} m`]);
  return c;
}

function voltasLayout(it: FeedItem, x: RunExtras) {
  const st = lapStructure(x.laps ?? [], x.planned?.workout_type);
  const cells = metricCells(it, x);
  const metricsH = Math.ceil(cells.length / 2) * METRIC_ROW;
  const head = 164;
  const structH = 64 + st.groups.length * GROUP_ROW;
  const tableH = 64 + 40 + st.rows.length * LAP_ROW + (st.hidden ? 40 : 0);
  const foot = 120;
  const panelH = head + metricsH + 28 + structH + 24 + tableH + foot;
  return { st, cells, metricsH, head, structH, tableH, panelH };
}

/** Altura do canvas: justa ao painel no Transparente; 4:5 (mín.) no Card. */
export function voltasHeight(it: FeedItem, x: RunExtras, transparent: boolean): number {
  const { panelH } = voltasLayout(it, x);
  return transparent ? panelH + 144 : Math.max(CARD_MIN_H, panelH + 144);
}

export function hasLaps(laps: ShareLap[] | null | undefined): boolean {
  return !!laps && laps.length >= 2;
}

function pill(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, text: string) {
  ctx.fillStyle = ORANGE;
  roundRect(ctx, x, y, w, 44, 22); ctx.fill();
  ctx.fillStyle = "#06251F"; ctx.font = `800 24px ${CANVAS_FONT}`; ctx.textAlign = "center";
  ctx.fillText(text, x + w / 2, y + 31);
  ctx.textAlign = "left";
}

// texto com contorno escuro quando não há painel (foto clara não engole o texto)
function txt(ctx: CanvasRenderingContext2D, panel: boolean, text: string, x: number, y: number) {
  if (!panel) {
    ctx.save();
    ctx.lineJoin = "round"; ctx.lineWidth = 6; ctx.strokeStyle = "rgba(0,0,0,0.6)";
    ctx.strokeText(text, x, y);
    ctx.restore();
  }
  ctx.fillText(text, x, y);
}

export function drawVoltas(
  ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras, hasPhoto: boolean, panel: boolean,
) {
  if (!hasLaps(x.laps)) return;
  const MUTED = panel ? MUTED_PANEL : MUTED_BARE;
  ctx.save();
  if (!panel) applySoftShadow(ctx); // sem painel: sombra no texto garante a leitura
  const L = voltasLayout(it, x);
  const px = hasPhoto ? W - PANEL_W - 48 : (W - PANEL_W) / 2;
  const py = Math.max(40, (H - L.panelH) / 2);
  const inner = px + PAD, innerR = px + PANEL_W - PAD, innerW = PANEL_W - 2 * PAD;

  // painel escuro (só no Card); no Transparente fica só o texto, solto
  if (panel) {
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 30; ctx.shadowOffsetY = 10;
    ctx.fillStyle = PANEL;
    roundRect(ctx, px, py, PANEL_W, L.panelH, 40); ctx.fill();
    ctx.restore();
    ctx.lineWidth = 3; ctx.strokeStyle = ORANGE;
    roundRect(ctx, px, py, PANEL_W, L.panelH, 40); ctx.stroke();
  }

  // título + data
  ctx.textAlign = "left"; ctx.fillStyle = ORANGE;
  let ts = 50;
  ctx.font = `italic 900 ${ts}px ${CANVAS_FONT}`;
  while (ctx.measureText(L.st.title).width > innerW && ts > 28) { ts -= 2; ctx.font = `italic 900 ${ts}px ${CANVAS_FONT}`; }
  txt(ctx, panel, fitText(ctx, L.st.title, innerW), inner, py + 84);
  // traço curvo sob o título, como nos stories de referência
  ctx.save();
  ctx.strokeStyle = ORANGE; ctx.lineWidth = 5; ctx.lineCap = "round";
  ctx.beginPath(); ctx.moveTo(inner, py + 104);
  ctx.quadraticCurveTo(inner + innerW * 0.5, py + 92, inner + innerW * 0.72, py + 100);
  ctx.stroke(); ctx.restore();
  ctx.font = `600 26px ${CANVAS_FONT}`; ctx.fillStyle = MUTED;
  txt(ctx, panel, x.date, inner, py + 138);

  // números (2 colunas)
  let y = py + L.head;
  const colW = innerW / 2;
  L.cells.forEach(([lab, val], i) => {
    const cx0 = inner + (i % 2) * colW;
    const cy0 = y + Math.floor(i / 2) * METRIC_ROW;
    ctx.fillStyle = MUTED; ctx.font = `600 24px ${CANVAS_FONT}`; txt(ctx, panel, lab, cx0, cy0 + 24);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 42px ${CANVAS_FONT}`; txt(ctx, panel, val, cx0, cy0 + 72);
  });
  y += L.metricsH + 28;

  // estrutura
  pill(ctx, inner, y, innerW, "ESTRUTURA DO TREINO");
  y += 64;
  for (const g of L.st.groups) {
    ctx.textAlign = "left"; ctx.fillStyle = "#FFFFFF"; ctx.font = `700 28px ${CANVAS_FONT}`;
    txt(ctx, panel, g.name, inner, y + 34);
    ctx.textAlign = "right"; ctx.fillStyle = MUTED; ctx.font = `600 25px ${CANVAS_FONT}`;
    txt(ctx, panel, fitText(ctx, g.detail, innerW * 0.62), innerR, y + 34);
    ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.fillRect(inner, y + GROUP_ROW - 2, innerW, 2);
    y += GROUP_ROW;
  }
  y += 24;

  // voltas
  pill(ctx, inner, y, innerW, L.st.unit === "Km" ? "PARCIAIS POR KM" : "BLOCOS");
  y += 64;
  const cN = inner + 4, cD = inner + innerW * 0.36, cT = inner + innerW * 0.62, cP = innerR;
  ctx.fillStyle = MUTED; ctx.font = `600 22px ${CANVAS_FONT}`;
  ctx.textAlign = "left"; txt(ctx, panel, L.st.unit, cN, y + 24);
  ctx.textAlign = "center"; txt(ctx, panel, "Distância", cD + 40, y + 24); txt(ctx, panel, "Tempo", cT, y + 24);
  ctx.textAlign = "right"; txt(ctx, panel, "Pace", cP, y + 24);
  y += 40;
  for (const r of L.st.rows) {
    const mid = y + LAP_ROW / 2 + 9;
    ctx.fillStyle = "#FFFFFF"; ctx.font = `700 27px ${CANVAS_FONT}`;
    ctx.textAlign = "left"; txt(ctx, panel, String(r.n), cN, mid);
    ctx.textAlign = "center";
    txt(ctx, panel, `${lapKm(r.lap)} km`, cD + 40, mid);
    txt(ctx, panel, fmtLapTime(r.lap.duration_s), cT, mid);
    const paceTxt = `${fmtPace(lapPaceSec(r.lap))}/km`;
    ctx.textAlign = "right";
    if (r.fast) {
      ctx.font = `800 27px ${CANVAS_FONT}`;
      const w = ctx.measureText(paceTxt).width + 26;
      ctx.fillStyle = ORANGE;
      roundRect(ctx, cP + 8 - w, y + 5, w, LAP_ROW - 10, (LAP_ROW - 10) / 2); ctx.fill();
      ctx.fillStyle = "#06251F"; ctx.fillText(paceTxt, cP - 5, mid);
    } else {
      ctx.fillStyle = "#FFFFFF"; txt(ctx, panel, paceTxt, cP, mid);
    }
    y += LAP_ROW;
  }
  if (L.st.hidden) {
    ctx.fillStyle = MUTED; ctx.font = `600 24px ${CANVAS_FONT}`; ctx.textAlign = "center";
    txt(ctx, panel, `+ ${L.st.hidden} ${L.st.unit === "Km" ? "km" : "blocos"}`, px + PANEL_W / 2, y + 30);
    y += 40;
  }

  // marca, dentro do painel
  ctx.textAlign = "left";
  drawBrand(ctx, px + PANEL_W / 2, py + L.panelH - 46, 40, true);
  ctx.restore();
}

// ---------------------------------------------------------------------------
// MINIMALISTA — números empilhados + rabisco da marca do percurso
// ---------------------------------------------------------------------------

const MIN_STEP = 104;
const MIN_TOP = 100;

function minimalCells(it: FeedItem, x: RunExtras): [string, string][] {
  const c: [string, string][] = [
    ["Distância", `${km2(it.distance_km)} km`],
    ["Ritmo", `${it.pace ?? "—"} /km`],
    ["Tempo", fmtDur(durOf(it))],
  ];
  if (it.elevation_gain != null) c.push(["Elevação", `${Math.round(it.elevation_gain)} m`]);
  if (x.cal) c.push(["Calorias", `${x.cal} kcal`]);
  if (it.avg_hr != null) c.push(["FC média", `${it.avg_hr} bpm`]);
  return c;
}

export function minimalHeight(it: FeedItem, x: RunExtras, transparent: boolean): number {
  const h = MIN_TOP + minimalCells(it, x).length * MIN_STEP + 150;
  return transparent ? h + 60 : Math.max(CARD_MIN_H, h + 60);
}

// rabisco determinístico (quando não há percurso): laço solto, "à mão"
function scribbleFallback(ctx: CanvasRenderingContext2D, bx: number, by: number, bw: number, bh: number) {
  const p = (u: number, v: number): [number, number] => [bx + u * bw, by + v * bh];
  ctx.beginPath();
  ctx.moveTo(...p(0.05, 0.42));
  ctx.bezierCurveTo(...p(0.3, 0.05), ...p(0.78, 0.02), ...p(0.92, 0.3));
  ctx.bezierCurveTo(...p(1.02, 0.55), ...p(0.7, 0.78), ...p(0.5, 0.6));
  ctx.bezierCurveTo(...p(0.3, 0.42), ...p(0.38, 0.95), ...p(0.7, 0.96));
  ctx.stroke();
}

function scribbleRoute(ctx: CanvasRenderingContext2D, pts: { lat: number; lon: number }[], bx: number, by: number, bw: number, bh: number) {
  const good = pts.filter((p) => p.lat && p.lon);
  if (good.length < 2) { scribbleFallback(ctx, bx, by, bw, bh); return; }
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const kx = Math.cos(((minLa + maxLa) / 2 * Math.PI) / 180);
  const spanLo = Math.max(1e-6, (maxLo - minLo) * kx), spanLa = Math.max(1e-6, maxLa - minLa);
  const scale = Math.min(bw / spanLo, bh / spanLa);
  const ox = bx + (bw - spanLo * scale) / 2, oy = by + (bh - spanLa * scale) / 2;
  // amostra ~160 pontos: traçado leve, "de mão"
  const step = Math.max(1, Math.floor(good.length / 160));
  ctx.beginPath();
  good.forEach((p, i) => {
    if (i % step && i !== good.length - 1) return;
    const X = ox + (p.lon - minLo) * kx * scale, Y = oy + (maxLa - p.lat) * scale;
    if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
  });
  ctx.stroke();
}

export function drawMinimal(
  ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras,
  pts: { lat: number; lon: number }[],
) {
  const cells = minimalCells(it, x);
  const stackH = cells.length * MIN_STEP;
  const total = MIN_TOP + stackH + 150;
  const top = Math.max(0, (H - total) / 2);
  const cx = W / 2;
  const y0 = top + MIN_TOP;

  // percurso REAL por TRÁS dos números, fino e deslocado pra direita: pega só
  // uma parte do texto, como nos stories de referência
  ctx.save();
  ctx.strokeStyle = ORANGE; ctx.lineWidth = 6; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.shadowColor = "rgba(0,0,0,0.3)"; ctx.shadowBlur = 5; ctx.shadowOffsetY = 2;
  scribbleRoute(ctx, pts, cx - 30, y0 + stackH * 0.16, 340, 320);
  ctx.restore();

  withShadow(ctx, () => {
    ctx.textAlign = "center";
    cells.forEach(([lab, val], i) => {
      const y = y0 + i * MIN_STEP;
      ctx.fillStyle = "rgba(255,255,255,0.92)"; ctx.font = `600 26px ${CANVAS_FONT}`;
      outlinedText(ctx, lab, cx, y, 3);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 54px ${CANVAS_FONT}`;
      outlinedText(ctx, val, cx, y + 52, 4);
    });
  });

  withShadow(ctx, () => drawBrand(ctx, cx, y0 + stackH + 60, 44, true));
}
