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
  { key: "card", label: "Card", transparent: false },
];

const TEAL = "#1FD9B8";
const TEAL_LIGHT = "#34E3C8";

export function summaryCells(s: PeriodSummary): [string, string][] {
  return [
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
    ["Maior", `${fmtKm(s.longestKm)} km`],
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
  const maxH = bottom - top - 50; // espaço do valor em cima
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
      ctx.font = `800 34px ${CANVAS_FONT}`;
      outlinedText(ctx, fmtKm(d.km), x + bw / 2, y - 16, 4);
    }
    ctx.font = `700 ${s.kind === "week" ? 34 : 30}px ${CANVAS_FONT}`;
    outlinedText(ctx, d.label, x + bw / 2, bottom + 48, 4);
  });
  ctx.textAlign = "left";
}

export function drawSummaryCard(
  ctx: CanvasRenderingContext2D, W: number, H: number,
  s: PeriodSummary, styleKey: string, photo: HTMLImageElement | null,
) {
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
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 36px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), cx, 190, 5);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 54px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, cx, 262, 6);

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
      ctx.fillStyle = up ? TEAL_LIGHT : "#FFFFFF"; ctx.font = `700 36px ${CANVAS_FONT}`;
      outlinedText(ctx, txt, cx, 562, 5);
    }
    ctx.textAlign = "left";
  });

  drawBars(ctx, s, left, right, 620, 900);

  const statsEnd = drawStatsSpread(ctx, left, right, 1030, summaryCells(s));

  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 110, H - 50), 46, true));
}
