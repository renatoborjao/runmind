// Card de compartilhar do RESUMO semanal/mensal (1080×1350). Mesma linguagem
// visual dos cards de corrida (contorno no texto, barras com halo, marca
// Ritmind única) — peças em share-canvas.

import { fmtKm, fmtPace, type PeriodSummary } from "./period-summary";
import {
  CANVAS_FONT, bottomScrim, drawBg, drawBrand, drawStatsSpread, fmtDur,
  outlinedText, roundRect, topScrim, withShadow,
} from "./share-canvas";

export interface SummaryCardStyle {
  key: string;
  label: string;
  transparent: boolean;
}

export const SUMMARY_STYLES: SummaryCardStyle[] = [
  { key: "sticker", label: "Sticker", transparent: true },
  { key: "barras", label: "Barras + dados", transparent: true },
  { key: "clean", label: "Clean", transparent: true },
  { key: "card", label: "Card", transparent: false },
];

const TEAL = "#1FD9B8";
const TEAL_LIGHT = "#34E3C8";

export function summaryCells(s: PeriodSummary): [string, string][] {
  return [
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
  ];
}

// barras do resumo (semana: por dia; mês: por semana) — km em cima de cada
// barra com corrida, rótulo embaixo
function drawBars(
  ctx: CanvasRenderingContext2D, s: PeriodSummary,
  left: number, right: number, top: number, bottom: number,
) {
  const n = s.bars.length;
  const gap = s.kind === "week" ? 26 : 40;
  const bw = (right - left - gap * (n - 1)) / n;
  const max = Math.max(1, ...s.bars.map((d) => d.km));
  const maxH = bottom - top - 58; // espaço do valor em cima
  const stub = 10;
  const r = Math.min(14, bw / 2);

  s.bars.forEach((d, i) => {
    const x = left + i * (bw + gap);
    const h = d.km > 0 ? Math.max(stub * 2, (maxH * d.km) / max) : stub;
    const y = bottom - h;

    withShadow(ctx, () => {
      if (d.km > 0) {
        ctx.fillStyle = "rgba(0,0,0,0.4)";
        roundRect(ctx, x - 2, y - 2, bw + 4, h + 4, r + 2); ctx.fill();
        const g = ctx.createLinearGradient(0, bottom, 0, y);
        g.addColorStop(0, TEAL); g.addColorStop(1, TEAL_LIGHT);
        ctx.fillStyle = g;
      } else {
        ctx.fillStyle = d.future ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.28)";
      }
      roundRect(ctx, x, y, bw, h, r); ctx.fill();
    });

    ctx.fillStyle = "#FFFFFF"; ctx.textAlign = "center";
    if (d.km > 0) {
      ctx.font = `800 42px ${CANVAS_FONT}`;
      outlinedText(ctx, fmtKm(d.km), x + bw / 2, y - 16, 6);
    }
    ctx.font = `800 38px ${CANVAS_FONT}`;
    outlinedText(ctx, d.label, x + bw / 2, bottom + 52, 6);
    if (d.sub) {
      ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.font = `700 30px ${CANVAS_FONT}`;
      outlinedText(ctx, d.sub, x + bw / 2, bottom + 92, 5);
      ctx.fillStyle = "#FFFFFF";
    }
  });
  ctx.textAlign = "left";
}

// BARRAS + DADOS — sem o número gigante: título, barras e a distância total
// EMBAIXO junto com ritmo/tempo (mesma leitura do sticker "Parciais + dados").
function drawBarsAndData(ctx: CanvasRenderingContext2D, W: number, H: number, s: PeriodSummary) {
  const cx = W / 2;
  const left = 110, right = W - 110;

  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), cx, 250, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 62px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, cx, 330, 8);

    const bits = [`${s.runs} ${s.runs === 1 ? "treino" : "treinos"}`];
    if (s.deltaPct != null) bits.push(`${s.deltaPct >= 0 ? "▲" : "▼"} ${Math.abs(s.deltaPct)}% ${s.vsLabel}`);
    ctx.fillStyle = "rgba(255,255,255,0.9)"; ctx.font = `700 38px ${CANVAS_FONT}`;
    outlinedText(ctx, bits.join("  ·  "), cx, 392, 5);
    ctx.textAlign = "left";
  });

  const bottom = 800;
  drawBars(ctx, s, left, right, 450, bottom);

  const statsY = bottom + (s.kind === "month" ? 170 : 140);
  const statsEnd = drawStatsSpread(ctx, left, right, statsY, [
    ["Distância", `${fmtKm(s.km, 2)} km`],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
  ], 70, 44);

  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 100, H - 50), 46, true));
}

// CLEAN — sem gráfico: título, datas e os números empilhados no centro
// (mesma linguagem do estilo "Central" das corridas).
function drawClean(ctx: CanvasRenderingContext2D, W: number, H: number, s: PeriodSummary) {
  const cx = W / 2;
  const items: [string, string][] = [
    ["Distância", `${fmtKm(s.km, 2)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
  ];
  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), cx, 200, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 62px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, cx, 280, 8);

    let y = 430;
    for (const [lab, val] of items) {
      ctx.fillStyle = "#FFFFFF"; ctx.font = `700 44px ${CANVAS_FONT}`;
      outlinedText(ctx, lab, cx, y, 5);
      ctx.font = `800 96px ${CANVAS_FONT}`;
      outlinedText(ctx, val, cx, y + 100, 9);
      y += 205;
    }
    ctx.textAlign = "left";
  });
  withShadow(ctx, () => drawBrand(ctx, cx, 1275, 50, true));
}

export function drawSummaryCard(
  ctx: CanvasRenderingContext2D, W: number, H: number,
  s: PeriodSummary, styleKey: string, photo: HTMLImageElement | null,
) {
  if (styleKey === "barras") { drawBarsAndData(ctx, W, H, s); return; }
  if (styleKey === "clean") { drawClean(ctx, W, H, s); return; }

  const cx = W / 2;
  const left = 110, right = W - 110;

  if (styleKey === "card") {
    drawBg(ctx, W, H, photo, null);
    if (photo) {
      topScrim(ctx, W); bottomScrim(ctx, W, H, 380);
    } else {
      // fundo escuro com um brilho teal suave (não fica chapado)
      const g = ctx.createRadialGradient(cx, 520, 40, cx, 520, 760);
      g.addColorStop(0, "rgba(31,217,184,0.20)"); g.addColorStop(1, "rgba(31,217,184,0)");
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    }
  }

  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), cx, 190, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 62px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, cx, 270, 8);

    // km em destaque: número grande + unidade menor, centralizados juntos
    const num = fmtKm(s.km), unit = " km";
    ctx.font = `800 210px ${CANVAS_FONT}`; const wn = ctx.measureText(num).width;
    ctx.font = `800 80px ${CANVAS_FONT}`; const wu = ctx.measureText(unit).width;
    const x0 = cx - (wn + wu) / 2;
    ctx.textAlign = "left";
    ctx.font = `800 210px ${CANVAS_FONT}`; outlinedText(ctx, num, x0, 490, 12);
    ctx.font = `800 80px ${CANVAS_FONT}`; outlinedText(ctx, unit, x0 + wn, 490, 7);

    if (s.deltaPct != null) {
      const up = s.deltaPct >= 0;
      const txt = `${up ? "▲" : "▼"} ${Math.abs(s.deltaPct)}% ${s.vsLabel}`;
      ctx.textAlign = "center";
      ctx.fillStyle = up ? TEAL_LIGHT : "#FFFFFF"; ctx.font = `800 42px ${CANVAS_FONT}`;
      outlinedText(ctx, txt, cx, 566, 6);
    }
    ctx.textAlign = "left";
  });

  drawBars(ctx, s, left, right, 616, 880);

  const statsEnd = drawStatsSpread(ctx, left, right, s.kind === "month" ? 1066 : 1036, summaryCells(s), 70, 44);

  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 110, H - 50), 46, true));
}
