// Card de compartilhar do RESUMO semanal/mensal (1080×1350). Mesma linguagem
// visual dos cards de corrida (contorno no texto, barras com halo, marca
// Ritmind única) — peças em share-canvas.

import { fmtKm, fmtPace, type PeriodSummary } from "./period-summary";
import {
  CANVAS_FONT, CARD_H, bottomScrim, drawBg, drawBrand, drawStatsSpread, fmtDur,
  outlinedText, roundRect, topScrim, withShadow,
} from "./share-canvas";

// MODELO (layout) e FUNDO são escolhas independentes: qualquer modelo sai
// transparente (sticker pra colar na foto) ou em card (fundo escuro ou foto).
export interface SummaryLayout {
  key: string;
  label: string;
  // altura própria do canvas (largura é sempre CARD_W) — o Deitado é uma
  // faixa justa no texto; sem isso o card dele viraria um retângulo vazio
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

// fundo dos estilos "Card": foto do atleta (escurecida pra leitura) ou
// escuro com brilho teal suave (não fica chapado)
function drawCardBg(ctx: CanvasRenderingContext2D, W: number, H: number, photo: HTMLImageElement | null) {
  drawBg(ctx, W, H, photo, null);
  if (photo) {
    ctx.fillStyle = "rgba(6,7,12,0.28)"; ctx.fillRect(0, 0, W, H);
    topScrim(ctx, W); bottomScrim(ctx, W, H, Math.round(H * 0.28));
    return;
  }
  const gy = Math.min(520, H / 2);
  const g = ctx.createRadialGradient(W / 2, gy, 40, W / 2, gy, Math.max(W, H) * 0.7);
  g.addColorStop(0, "rgba(31,217,184,0.20)"); g.addColorStop(1, "rgba(31,217,184,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
}

// DEITADO — faixa horizontal justa no texto (canvas de 440px de altura, igual
// ao espírito do "Cantinho" das corridas): marca, título + datas e a linha
// Distância/Treinos/Tempo/Ritmo lado a lado.
function drawDeitado(ctx: CanvasRenderingContext2D, W: number, _H: number, s: PeriodSummary) {
  const left = 64, right = W - 64;
  withShadow(ctx, () => drawBrand(ctx, left, 96, 46, false));
  withShadow(ctx, () => {
    ctx.textAlign = "left";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 38px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), left, 172, 5);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 54px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, left, 236, 7);
  });
  drawStatsSpread(ctx, left, right, 312, [
    ["Distância", `${fmtKm(s.km, 1)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo", `${fmtPace(s.paceSec)} /km`],
  ], 62, 40);
}

const WEEK_HEAD = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

// cabeçalho comum dos cards novos: eyebrow teal + período em branco
function drawHeader(ctx: CanvasRenderingContext2D, cx: number, s: PeriodSummary, y: number) {
  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, s.title.toUpperCase(), cx, y, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 62px ${CANVAS_FONT}`;
    outlinedText(ctx, s.label, cx, y + 76, 8);
    ctx.textAlign = "left";
  });
}

// cor da célula do calendário: mais km = teal mais forte
function cellFill(km: number, max: number, future: boolean): string {
  if (km <= 0) return future ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.16)";
  const a = 0.38 + 0.62 * Math.min(1, km / max);
  return `rgba(31,217,184,${a.toFixed(2)})`;
}

// CALENDÁRIO — um quadrado por dia (estilo "contribuições do GitHub"), verde
// mais forte = mais km. Mês: grade seg–dom; semana: 7 dias grandes.
function drawCalendario(ctx: CanvasRenderingContext2D, W: number, H: number, s: PeriodSummary) {
  const cx = W / 2, left = 110, right = W - 110;
  const gap = 14, cols = 7;
  const cell = (right - left - gap * (cols - 1)) / cols;
  const max = Math.max(1, ...s.days.map((d) => d.km));
  drawHeader(ctx, cx, s, 190);

  const week = s.kind === "week";
  const cellH = week ? 230 : cell;
  const top = week ? 430 : 400;
  // semana: rótulo do dia DENTRO da célula; mês: cabeçalho Seg…Dom em cima
  if (!week) {
    withShadow(ctx, () => {
      ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF"; ctx.font = `800 30px ${CANVAS_FONT}`;
      WEEK_HEAD.forEach((h, i) => outlinedText(ctx, h, left + i * (cell + gap) + cell / 2, top - 22, 4));
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
      roundRect(ctx, x, y, cell, cellH, 18); ctx.fill();
    });
    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
    if (week) {
      ctx.font = `800 34px ${CANVAS_FONT}`;
      outlinedText(ctx, WEEK_HEAD[d.weekday], x + cell / 2, y + 54, 4);
      if (d.km > 0) {
        ctx.font = `800 40px ${CANVAS_FONT}`;
        outlinedText(ctx, fmtKm(d.km), x + cell / 2, y + 150, 5);
        ctx.font = `700 26px ${CANVAS_FONT}`;
        outlinedText(ctx, "km", x + cell / 2, y + 188, 3);
      }
    } else {
      ctx.textAlign = "left"; ctx.font = `700 22px ${CANVAS_FONT}`;
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.fillText(String(d.day), x + 12, y + 30);
      if (d.km > 0) {
        ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF"; ctx.font = `800 32px ${CANVAS_FONT}`;
        outlinedText(ctx, fmtKm(d.km), x + cell / 2, y + cell / 2 + 22, 4);
      }
    }
    ctx.textAlign = "left";
  });

  const statsEnd = drawStatsSpread(ctx, left, right, bottom + 90, [
    ["Distância", `${fmtKm(s.km)} km`],
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
  ], 62, 40);
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 90, H - 40), 46, true));
}

// META — anel de progresso: km feitos × meta de km do PLANO no período
function drawMeta(ctx: CanvasRenderingContext2D, W: number, H: number, s: PeriodSummary) {
  const cx = W / 2, cy = 640, r = 280, lw = 54;
  const goal = s.goalKm && s.goalKm > 0 ? s.goalKm : Math.max(s.km, 1);
  const frac = s.km / goal;
  drawHeader(ctx, cx, s, 190);

  const a0 = -Math.PI / 2;
  withShadow(ctx, () => {
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = lw + 8;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = lw;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
  });
  ctx.save();
  ctx.lineCap = "round"; ctx.lineWidth = lw;
  ctx.shadowColor = TEAL; ctx.shadowBlur = 24;
  const g = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
  g.addColorStop(0, TEAL); g.addColorStop(1, TEAL_LIGHT);
  ctx.strokeStyle = g;
  ctx.beginPath(); ctx.arc(cx, cy, r, a0, a0 + Math.PI * 2 * Math.min(frac, 1)); ctx.stroke();
  if (frac > 1) {
    // passou da meta: segunda volta mais clara por cima
    ctx.strokeStyle = "#B9FFF2"; ctx.lineWidth = lw * 0.45;
    ctx.beginPath(); ctx.arc(cx, cy, r, a0, a0 + Math.PI * 2 * Math.min(frac - 1, 1)); ctx.stroke();
  }
  ctx.restore();

  withShadow(ctx, () => {
    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
    ctx.font = `800 150px ${CANVAS_FONT}`; outlinedText(ctx, fmtKm(s.km), cx, cy + 30, 10);
    ctx.font = `700 46px ${CANVAS_FONT}`; outlinedText(ctx, `de ${fmtKm(goal, 0)} km`, cx, cy + 100, 5);
    const pct = Math.round(frac * 100);
    const msg = frac >= 1
      ? `Meta ${s.kind === "week" ? "da semana" : "do mês"} batida! ${pct}%`
      : `${pct}% da meta ${s.kind === "week" ? "da semana" : "do mês"}`;
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 46px ${CANVAS_FONT}`;
    outlinedText(ctx, msg, cx, cy + r + 110, 6);
    ctx.textAlign = "left";
  });

  const statsEnd = drawStatsSpread(ctx, 110, W - 110, cy + r + 190, [
    ["Treinos", String(s.runs)],
    ["Tempo", s.seconds > 0 ? fmtDur(s.seconds) : "—"],
    ["Ritmo médio", `${fmtPace(s.paceSec)} /km`],
  ], 58, 38);
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 80, H - 36), 44, true));
}

export function drawSummaryCard(
  ctx: CanvasRenderingContext2D, W: number, H: number,
  s: PeriodSummary, layout: string, background: SummaryBackground,
  photo: HTMLImageElement | null,
) {
  if (background === "card") drawCardBg(ctx, W, H, photo);
  if (layout === "barras") { drawBarsAndData(ctx, W, H, s); return; }
  if (layout === "clean") { drawClean(ctx, W, H, s); return; }
  if (layout === "deitado") { drawDeitado(ctx, W, H, s); return; }
  if (layout === "calendario") { drawCalendario(ctx, W, H, s); return; }
  if (layout === "meta") { drawMeta(ctx, W, H, s); return; }
  drawDestaque(ctx, W, H, s);
}

// DESTAQUE — km gigante no topo, variação, barras e a linha de dados
function drawDestaque(ctx: CanvasRenderingContext2D, W: number, H: number, s: PeriodSummary) {
  const cx = W / 2;
  const left = 110, right = W - 110;


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
