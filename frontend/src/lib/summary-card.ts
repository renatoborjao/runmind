// Card de compartilhar do RESUMO semanal/mensal. Desenha num quadro de
// 1080×1350 e o editor CORTA justo ao conteúdo (paintTight) — colado no story
// vira um sticker compacto, não um bloco que cobre a foto. Enxuto, na escala
// do Strava: um cabeçalho só (o período), números médios, barras sem datas.

import { fmtKm, fmtPace, type PeriodSummary } from "./period-summary";
import {
  CANVAS_FONT, CARD_H, drawBrand, drawStatsSpread, fmtDur,
  outlinedText, roundRect, withShadow,
} from "./share-canvas";

// MODELO (layout) e FUNDO são escolhas independentes: qualquer modelo sai
// transparente (sticker pra colar na foto) ou em card (fundo escuro ou foto).
export interface SummaryLayout {
  key: string;
  label: string;
  // altura do quadro de DESENHO (o card final é cortado justo ao conteúdo)
  height?: number;
}

export const SUMMARY_LAYOUTS: SummaryLayout[] = [
  { key: "destaque", label: "Destaque" },
  { key: "barras", label: "Barras + dados" },
  { key: "clean", label: "Clean" },
  { key: "deitado", label: "Deitado", height: 440 },
  { key: "calendario", label: "Calendário" },
  { key: "meta", label: "Meta" },
];

export function summaryCanvasHeight(layoutKey: string): number {
  return SUMMARY_LAYOUTS.find((l) => l.key === layoutKey)?.height ?? CARD_H;
}

export type SummaryBackground = "transparent" | "card";

const TEAL = "#1FD9B8";
const TEAL_LIGHT = "#34E3C8";

// escala única dos números do resumo (padrão Strava: rótulo ~metade do valor)
const VAL = 56, LAB = 30, BRAND = 40;

function periodWord(s: PeriodSummary): string {
  return s.kind === "week" ? "semana" : "mês";
}

// cabeçalho ÚNICO: o período em branco (o "Resumo do mês" em cima era
// redundante com "Setembro 2026").
function drawHeader(ctx: CanvasRenderingContext2D, x: number, s: PeriodSummary, y: number, align: CanvasTextAlign = "center") {
  withShadow(ctx, () => {
    ctx.textAlign = align;
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 46px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, x, y, 0);
    ctx.textAlign = "left";
  });
}

// barras (semana: por dia; mês: por semana). Mês: só as semanas que já
// começaram (a S5 vazia do futuro era ruído); sem a linha de datas embaixo.
function drawBars(
  ctx: CanvasRenderingContext2D, s: PeriodSummary,
  left: number, right: number, top: number, bottom: number,
) {
  const bars = s.kind === "month" ? s.bars.filter((b) => !b.future) : s.bars;
  const n = Math.max(1, bars.length);
  const gap = s.kind === "week" ? 22 : 36;
  // barra fina e o conjunto centralizado (4 semanas não viram "tijolos")
  const bw = Math.min(110, (right - left - gap * (n - 1)) / n);
  left += (right - left - (bw * n + gap * (n - 1))) / 2;
  const max = Math.max(1, ...bars.map((d) => d.km));
  const maxH = bottom - top - 44; // espaço do valor em cima
  const stub = 8;
  const r = Math.min(12, bw / 2);

  bars.forEach((d, i) => {
    const x = left + i * (bw + gap);
    const h = d.km > 0 ? Math.max(stub * 2, (maxH * d.km) / max) : stub;
    const y = bottom - h;

    withShadow(ctx, () => {
      if (d.km > 0) {
        const g = ctx.createLinearGradient(0, bottom, 0, y);
        g.addColorStop(0, TEAL); g.addColorStop(1, TEAL_LIGHT);
        ctx.fillStyle = g;
      } else {
        ctx.fillStyle = d.future ? "rgba(255,255,255,0.14)" : "rgba(255,255,255,0.3)";
      }
      roundRect(ctx, x, y, bw, h, r); ctx.fill();

      ctx.fillStyle = "#FFFFFF"; ctx.textAlign = "center";
      if (d.km > 0) {
        ctx.font = `800 30px ${CANVAS_FONT}`;
        outlinedText(ctx, fmtKm(d.km), x + bw / 2, y - 12, 0);
      }
      ctx.font = `700 28px ${CANVAS_FONT}`;
      outlinedText(ctx, d.label, x + bw / 2, bottom + 40, 0);
    });
  });
  ctx.textAlign = "left";
}

function brandBelow(ctx: CanvasRenderingContext2D, cx: number, y: number) {
  withShadow(ctx, () => drawBrand(ctx, cx, y, BRAND, true));
}

// DESTAQUE — período, km em destaque + variação, barras e a linha de dados
function drawDestaque(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const cx = W / 2, left = 150, right = W - 150;
  drawHeader(ctx, cx, s, 200);

  withShadow(ctx, () => {
    const num = fmtKm(s.km), unit = " km";
    ctx.font = `800 140px ${CANVAS_FONT}`; const wn = ctx.measureText(num).width;
    ctx.font = `800 56px ${CANVAS_FONT}`; const wu = ctx.measureText(unit).width;
    const x0 = cx - (wn + wu) / 2;
    ctx.textAlign = "left"; ctx.fillStyle = "#FFFFFF";
    ctx.font = `800 140px ${CANVAS_FONT}`; outlinedText(ctx, num, x0, 350, 0);
    ctx.font = `800 56px ${CANVAS_FONT}`; outlinedText(ctx, unit, x0 + wn, 350, 0);
    if (s.deltaPct != null) {
      const up = s.deltaPct >= 0;
      ctx.textAlign = "center";
      ctx.fillStyle = up ? TEAL_LIGHT : "#FFFFFF"; ctx.font = `700 30px ${CANVAS_FONT}`;
      outlinedText(ctx, `${up ? "▲" : "▼"} ${Math.abs(s.deltaPct)}% ${s.vsLabel}`, cx, 404, 0);
    }
    ctx.textAlign = "left";
  });

  drawBars(ctx, s, left, right, 450, 640);
  const statsEnd = drawStatsSpread(ctx, left, right, 740, summaryCells(s), VAL, LAB);
  brandBelow(ctx, cx, statsEnd + 90);
}

// BARRAS + DADOS — sem o número gigante: período, barras e os dados embaixo
function drawBarsAndData(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const cx = W / 2, left = 150, right = W - 150;
  drawHeader(ctx, cx, s, 200);
  drawBars(ctx, s, left, right, 250, 500);
  const statsEnd = drawStatsSpread(ctx, left, right, 600, [
    ["Distância", `${fmtKm(s.km, 1)} km`],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
  ], VAL, LAB);
  brandBelow(ctx, cx, statsEnd + 90);
}

// CLEAN — sem gráfico: período e os números empilhados no centro
// (mesma linguagem do "Central" das corridas).
function drawClean(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const cx = W / 2;
  const items: [string, string][] = [
    ["Distância", `${fmtKm(s.km, 1)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
  ];
  drawHeader(ctx, cx, s, 200);
  let y = 300;
  withShadow(ctx, () => {
    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
    for (const [lab, val] of items) {
      ctx.font = `700 34px ${CANVAS_FONT}`; outlinedText(ctx, lab, cx, y, 0);
      ctx.font = `800 76px ${CANVAS_FONT}`; outlinedText(ctx, val, cx, y + 80, 0);
      y += 160;
    }
    ctx.textAlign = "left";
  });
  brandBelow(ctx, cx, y + 10);
}

// DEITADO — faixa horizontal: marca, período e a linha de dados lado a lado.
function drawDeitado(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const left = 64, right = W - 64;
  withShadow(ctx, () => drawBrand(ctx, left, 96, BRAND, false));
  drawHeader(ctx, left, s, 186, "left");
  drawStatsSpread(ctx, left, right, 262, [
    ["Distância", `${fmtKm(s.km, 1)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo", `${fmtPace(s.paceSec)} /km`],
  ], VAL, LAB);
}

const WEEK_HEAD = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

// cor da célula do calendário: mais km = teal mais forte
function cellFill(km: number, max: number, future: boolean): string {
  if (km <= 0) return future ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.16)";
  const a = 0.38 + 0.62 * Math.min(1, km / max);
  return `rgba(31,217,184,${a.toFixed(2)})`;
}

// CALENDÁRIO — um quadrado por dia (estilo "contribuições do GitHub"), teal
// mais forte = mais km. Mês: grade seg–dom; semana: 7 dias grandes.
function drawCalendario(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const cx = W / 2, left = 150, right = W - 150;
  const gap = 12, cols = 7;
  const cell = (right - left - gap * (cols - 1)) / cols;
  const max = Math.max(1, ...s.days.map((d) => d.km));
  drawHeader(ctx, cx, s, 200);

  const week = s.kind === "week";
  const cellH = week ? 190 : cell;
  const top = week ? 250 : 290;
  if (!week) {
    withShadow(ctx, () => {
      ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF"; ctx.font = `700 24px ${CANVAS_FONT}`;
      WEEK_HEAD.forEach((h, i) => outlinedText(ctx, h, left + i * (cell + gap) + cell / 2, top - 18, 0));
    });
  }
  const firstCol = s.days[0]?.weekday ?? 0;
  let bottom = top;
  s.days.forEach((d, i) => {
    const pos = week ? i : firstCol + i;
    const col = pos % cols, row = Math.floor(pos / cols);
    const x = left + col * (cell + gap), y = top + row * (cellH + gap);
    bottom = Math.max(bottom, y + cellH);
    withShadow(ctx, () => {
      ctx.fillStyle = cellFill(d.km, max, d.future);
      roundRect(ctx, x, y, cell, cellH, 14); ctx.fill();
      ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
      if (week) {
        ctx.font = `800 28px ${CANVAS_FONT}`;
        outlinedText(ctx, WEEK_HEAD[d.weekday], x + cell / 2, y + 46, 0);
        if (d.km > 0) {
          ctx.font = `800 34px ${CANVAS_FONT}`;
          outlinedText(ctx, fmtKm(d.km), x + cell / 2, y + 128, 0);
        }
      } else if (d.km > 0) {
        // mês: só o km no dia com corrida (o número do dia era ruído)
        ctx.font = `800 26px ${CANVAS_FONT}`;
        outlinedText(ctx, fmtKm(d.km), x + cell / 2, y + cell / 2 + 9, 0);
      }
    });
    ctx.textAlign = "left";
  });

  const statsEnd = drawStatsSpread(ctx, left, right, bottom + 80, [
    ["Distância", `${fmtKm(s.km, 1)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
  ], VAL, LAB);
  brandBelow(ctx, cx, statsEnd + 90);
}

// META — anel de progresso: km feitos × meta de km do PLANO no período
function drawMeta(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary) {
  const cx = W / 2, cy = 480, r = 210, lw = 38;
  const goal = s.goalKm && s.goalKm > 0 ? s.goalKm : Math.max(s.km, 1);
  const frac = s.km / goal;
  drawHeader(ctx, cx, s, 200);

  const a0 = -Math.PI / 2;
  withShadow(ctx, () => {
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = lw;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    const g = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    g.addColorStop(0, TEAL); g.addColorStop(1, TEAL_LIGHT);
    ctx.strokeStyle = g;
    ctx.beginPath(); ctx.arc(cx, cy, r, a0, a0 + Math.PI * 2 * Math.min(frac, 1)); ctx.stroke();
    if (frac > 1) {
      // passou da meta: segunda volta mais clara por cima
      ctx.strokeStyle = "#B9FFF2"; ctx.lineWidth = lw * 0.45;
      ctx.beginPath(); ctx.arc(cx, cy, r, a0, a0 + Math.PI * 2 * Math.min(frac - 1, 1)); ctx.stroke();
    }

    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
    ctx.font = `800 110px ${CANVAS_FONT}`; outlinedText(ctx, fmtKm(s.km), cx, cy + 22, 0);
    ctx.font = `700 34px ${CANVAS_FONT}`; outlinedText(ctx, `de ${fmtKm(goal, 0)} km`, cx, cy + 76, 0);
    const pct = Math.round(frac * 100);
    const msg = frac >= 1 ? `Meta do ${periodWord(s)} batida! ${pct}%` : `${pct}% da meta do ${periodWord(s)}`;
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 36px ${CANVAS_FONT}`;
    outlinedText(ctx, msg, cx, cy + r + 90, 0);
    ctx.textAlign = "left";
  });

  const statsEnd = drawStatsSpread(ctx, 150, W - 150, cy + r + 180, summaryCells(s), VAL, LAB);
  brandBelow(ctx, cx, statsEnd + 90);
}

export function summaryCells(s: PeriodSummary): [string, string][] {
  return [
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
  ];
}

// só o CONTEÚDO (sem fundo) — o fundo e o corte justo são do paintTight
export function drawSummaryContent(ctx: CanvasRenderingContext2D, W: number, s: PeriodSummary, layout: string) {
  if (layout === "barras") return drawBarsAndData(ctx, W, s);
  if (layout === "clean") return drawClean(ctx, W, s);
  if (layout === "deitado") return drawDeitado(ctx, W, s);
  if (layout === "calendario") return drawCalendario(ctx, W, s);
  if (layout === "meta") return drawMeta(ctx, W, s);
  drawDestaque(ctx, W, s);
}
