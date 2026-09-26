// Cards de compartilhar da CORRIDA que usam o que só o Ritmind tem (o plano e o
// coach) + o "número de peito". Mesma linguagem visual dos demais (contorno no
// texto, marca única) — peças em share-canvas.

import type { FeedItem } from "./api";
import {
  CANVAS_FONT, drawBrand, drawBrandOnLight, drawPill, drawStatsSpread, fitText,
  fmtDur, outlinedText, roundRect, withShadow, wrapLines,
} from "./share-canvas";

const TEAL_LIGHT = "#34E3C8";

// sessão do plano que essa corrida cumpriu (vem do backend)
export interface PlannedSession {
  workout_type: string;
  distance_km: number | null;
  pace_min: string | null;   // "6:15"
  pace_max: string | null;   // "6:25"
  duration_min: number | null;
}

export interface RunExtras {
  date: string;                    // "26 set 2026"
  planned: PlannedSession | null;
  quote: string | null;            // frase curta do coach sobre o treino
}

function paceToSec(p: string | null | undefined): number | null {
  if (!p) return null;
  const m = /^(\d+):(\d{2})/.exec(p.trim());
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}
function km2(v: number): string { return v.toFixed(2).replace(".", ","); }
function km1(v: number): string { return v.toFixed(1).replace(".", ","); }
function durOf(it: FeedItem): number { return it.duration_s || (it.duration_min || 0) * 60; }
// tempo sem segundos ("48min" / "1h20") — cabe na coluna do Plano × feito
function durShort(sec: number): string {
  const m = Math.round(sec / 60), h = Math.floor(m / 60);
  return h > 0 ? `${h}h${String(m % 60).padStart(2, "0")}` : `${m}min`;
}

// o plano tem algo pra comparar? (sessão sem distância, tempo nem ritmo não
// rende o card — só o nome do treino)
export function planHasTargets(p: PlannedSession | null | undefined): boolean {
  return !!p && !!(p.distance_km || p.duration_min || p.pace_min || p.pace_max);
}

// veredito curto do Plano × feito: distância (ou tempo, na sessão por tempo)
// cumprida? ritmo vs alvo?
export function planVerdict(it: FeedItem, p: PlannedSession): string {
  const parts: string[] = [];
  if (p.distance_km) {
    const pct = Math.round((it.distance_km / p.distance_km) * 100);
    parts.push(pct >= 95 ? "✅ Distância cumprida" : `${pct}% da distância`);
  } else if (p.duration_min) {
    const pct = Math.round((durOf(it) / (p.duration_min * 60)) * 100);
    parts.push(pct >= 95 ? "✅ Tempo cumprido" : `${pct}% do tempo`);
  }
  const done = paceToSec(it.pace), lo = paceToSec(p.pace_min), hi = paceToSec(p.pace_max) ?? lo;
  if (done != null && lo != null && hi != null) {
    const fast = Math.min(lo, hi), slow = Math.max(lo, hi);
    if (done < fast) parts.push(`${fast - done}s/km mais rápido`);
    else if (done > slow) parts.push(`${done - slow}s/km mais lento`);
    else parts.push("no ritmo alvo");
  }
  return parts.join(" · ");
}

// PLANO × FEITO — o que o coach passou lado a lado com o que o atleta fez
export function drawPlanoFeito(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras) {
  const p = x.planned;
  const cx = W / 2, left = 110;
  const colP = 560, colF = 830;
  if (!p) return;

  const plannedPace = p.pace_min && p.pace_max && p.pace_min !== p.pace_max
    ? `${p.pace_min}–${p.pace_max}` : (p.pace_min || p.pace_max || null);
  // distância e ritmo sempre (o que o plano não fixou aparece "livre"); tempo
  // só quando o plano é por tempo
  const rows: [string, string, string][] = [];
  rows.push(["Distância", p.distance_km ? `${km1(p.distance_km)} km` : "livre", `${km2(it.distance_km)} km`]);
  if (p.duration_min) rows.push(["Tempo", durShort(p.duration_min * 60), durShort(durOf(it))]);
  rows.push(["Ritmo", plannedPace ?? "livre", it.pace ?? "—"]);
  const verdict = planVerdict(it, p);

  // bloco inteiro centralizado na vertical
  const rowH = 140;
  const blockH = 340 + rows.length * rowH + (verdict ? 130 : 0) + 130;
  const top = Math.max(60, (H - blockH) / 2);

  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, "PLANO × FEITO", cx, top + 50, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 66px ${CANVAS_FONT}`;
    outlinedText(ctx, fitText(ctx, p.workout_type, W - 160), cx, top + 135, 8);
    ctx.font = `700 34px ${CANVAS_FONT}`; ctx.fillStyle = "rgba(255,255,255,0.9)";
    outlinedText(ctx, x.date, cx, top + 190, 4);
  });

  let y = top + 300;
  withShadow(ctx, () => {
    ctx.textAlign = "center"; ctx.font = `800 32px ${CANVAS_FONT}`;
    ctx.fillStyle = "rgba(255,255,255,0.8)"; outlinedText(ctx, "PLANEJADO", colP, y, 4);
    ctx.fillStyle = TEAL_LIGHT; outlinedText(ctx, "FEITO", colF, y, 4);
  });
  y += 40;
  for (const [lab, pv, fv] of rows) {
    ctx.fillStyle = "rgba(255,255,255,0.28)"; ctx.fillRect(left, y, W - 2 * left, 3);
    const base = y + 96;
    withShadow(ctx, () => {
      ctx.textAlign = "left"; ctx.fillStyle = "#FFFFFF"; ctx.font = `700 38px ${CANVAS_FONT}`;
      outlinedText(ctx, lab, left, base - 8, 5);
      ctx.textAlign = "center";
      ctx.font = pv === "livre" ? `italic 700 42px ${CANVAS_FONT}` : `700 50px ${CANVAS_FONT}`;
      ctx.fillStyle = pv === "livre" ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.85)";
      outlinedText(ctx, pv, colP, base, 6);
      // valor do FEITO: encolhe a fonte até caber na coluna (nunca corta)
      const maxW = 2 * (W - 70 - colF);
      let fs = 58;
      ctx.font = `800 ${fs}px ${CANVAS_FONT}`;
      while (ctx.measureText(fv).width > maxW && fs > 34) { fs -= 2; ctx.font = `800 ${fs}px ${CANVAS_FONT}`; }
      ctx.fillStyle = "#FFFFFF";
      outlinedText(ctx, fv, colF, base, 7);
    });
    y += rowH;
  }
  ctx.fillStyle = "rgba(255,255,255,0.28)"; ctx.fillRect(left, y, W - 2 * left, 3);

  if (verdict) { drawPill(ctx, cx, y + 120, verdict, 40, TEAL_LIGHT); y += 130; }
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(y + 120, H - 40), 46, true));
}

// COACH DIZ — frase do coach sobre o treino em destaque + os números
export function drawCoachDiz(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras) {
  const cx = W / 2, left = 110, right = W - 110;
  const quote = (x.quote || "").trim();
  if (!quote) return;

  ctx.font = `800 58px ${CANVAS_FONT}`;
  const lines = wrapLines(ctx, quote, right - left, 5);
  const lineH = 76;
  // bloco centralizado na vertical: aspas + frase + assinatura + dados + marca
  const blockH = 150 + lines.length * lineH + 90 + 200 + 120;
  let y = Math.max(140, (H - blockH) / 2) + 150;

  withShadow(ctx, () => {
    ctx.textAlign = "left";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 260px Georgia, serif`;
    outlinedText(ctx, "“", left - 12, y + 40, 8);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 58px ${CANVAS_FONT}`;
    lines.forEach((ln, i) => outlinedText(ctx, ln, left, y + 60 + i * lineH, 7));
    y += 60 + (lines.length - 1) * lineH + 80;
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 38px ${CANVAS_FONT}`;
    outlinedText(ctx, "— Coach Ritmind", left, y, 5);
  });

  const statsEnd = drawStatsSpread(ctx, left, right, y + 120, [
    ["Distância", `${km2(it.distance_km)} km`],
    ["Ritmo", `${it.pace ?? "—"} /km`],
    ["Tempo", fmtDur(durOf(it))],
  ], 60, 38);
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 100, H - 40), 46, true));
}

// NÚMERO DE PEITO — o card vira um número de prova: km como "número", data,
// ritmo/tempo e o tipo do treino. Papel opaco (é o próprio sticker).
export function drawPeito(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras) {
  const cx = W / 2, cy = H / 2;
  const bw = 880, bh = 640, bx = cx - bw / 2, by = cy - bh / 2;

  ctx.save();
  ctx.translate(cx, cy); ctx.rotate(-0.04); ctx.translate(-cx, -cy);

  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 34; ctx.shadowOffsetY = 12;
  ctx.fillStyle = "#FAF8F2";
  roundRect(ctx, bx, by, bw, bh, 30); ctx.fill();
  ctx.restore();

  // faixa teal no topo com a marca e a data
  ctx.save();
  roundRect(ctx, bx, by, bw, bh, 30); ctx.clip();
  const g = ctx.createLinearGradient(bx, 0, bx + bw, 0);
  g.addColorStop(0, "#1FD9B8"); g.addColorStop(1, "#34E3C8");
  ctx.fillStyle = g; ctx.fillRect(bx, by, bw, 118);
  // faixa fina no pé
  ctx.fillRect(bx, by + bh - 26, bw, 26);
  ctx.restore();

  ctx.textAlign = "left"; ctx.fillStyle = "#08322B"; ctx.font = `800 46px ${CANVAS_FONT}`;
  ctx.fillText("RITMIND RUN", bx + 70, by + 76);
  ctx.textAlign = "right"; ctx.font = `800 34px ${CANVAS_FONT}`;
  ctx.fillText(x.date.toUpperCase(), bx + bw - 70, by + 74);

  // furos do alfinete nos 4 cantos
  for (const [hx, hy] of [[bx + 38, by + 150], [bx + bw - 38, by + 150], [bx + 38, by + bh - 62], [bx + bw - 38, by + bh - 62]]) {
    ctx.beginPath(); ctx.arc(hx, hy, 13, 0, Math.PI * 2);
    ctx.fillStyle = "#D9D6CC"; ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = "#B9B5A8"; ctx.stroke();
  }

  // o "número": km
  ctx.textAlign = "center"; ctx.fillStyle = "#15161C";
  ctx.font = `900 250px ${CANVAS_FONT}`;
  ctx.fillText(km2(it.distance_km), cx, by + 360);
  ctx.font = `800 36px ${CANVAS_FONT}`; ctx.fillStyle = "#5B5D68";
  ctx.fillText("Q U I L Ô M E T R O S", cx, by + 462);

  ctx.font = `800 44px ${CANVAS_FONT}`; ctx.fillStyle = "#15161C";
  const line = [`${it.pace ?? "—"} /km`, fmtDur(durOf(it)), it.avg_hr != null ? `${it.avg_hr} bpm` : null]
    .filter(Boolean).join("  ·  ");
  ctx.fillText(line, cx, by + 532);
  const kind = x.planned?.workout_type;
  if (kind) {
    ctx.font = `800 34px ${CANVAS_FONT}`; ctx.fillStyle = "#0E9C85";
    ctx.fillText(fitText(ctx, kind.toUpperCase(), bw - 180), cx, by + 586);
  } else {
    drawBrandOnLight(ctx, cx, by + 590, 34, true);
  }
  ctx.textAlign = "left";
  ctx.restore();
}
