// Cards de compartilhar da CORRIDA que usam o que só o Ritmind tem (o plano e o
// coach) + o "número de peito". Mesma linguagem visual dos demais (contorno no
// texto, marca única) — peças em share-canvas.

import type { FeedItem, PlanPhase } from "./api";
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
  // ritmo como o plano descreve (vem dos PASSOS do treino): "6:20–6:45",
  // "6:20–6:45 → 5:25–5:40", "4:50–5:05 (tiros)"
  pace_label?: string | null;
  // treino estruturado (progressivo/tiros): NÃO compara com a média do atleta
  pace_structured?: boolean;
  // o EXECUTADO fase a fase (voltas do relógio × passos do plano); null sem
  // Garmin — aí o card não inventa comparação de ritmo
  phases?: PlanPhase[] | null;
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
  return !!p && !!(p.distance_km || p.duration_min || p.pace_min || p.pace_max || p.pace_label);
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
  // ritmo só se compara em treino CONTÍNUO (a média de um progressivo/fartlek
  // mistura blocos e daria veredito falso)
  const done = paceToSec(it.pace), lo = paceToSec(p.pace_min), hi = paceToSec(p.pace_max) ?? lo;
  if (!p.pace_structured && done != null && lo != null && hi != null) {
    const fast = Math.min(lo, hi), slow = Math.max(lo, hi);
    if (done < fast) parts.push(`${fast - done}s/km mais rápido`);
    else if (done > slow) parts.push(`${done - slow}s/km mais lento`);
    else parts.push("no ritmo alvo");
  }
  return parts.join(" · ");
}

function fmtPaceSec(sec: number | null | undefined): string {
  if (sec == null) return "—";
  const t = Math.round(sec);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

const OK_COLOR = "#1FD9B8", FAST_COLOR = "#FFB547", SLOW_COLOR = "#9AA0B4";
// folga de pace do veredito "no alvo" (igual ao _PACE_SLACK do backend)
const PACE_SLACK = 0.03;

function repColor(pace: number | null, ok: boolean | null, lo: number | null): string {
  if (ok) return OK_COLOR;
  if (pace != null && lo != null && pace < lo) return FAST_COLOR;
  return SLOW_COLOR;
}

// cabeçalho do Plano × feito (título + treino + data), centrado em `top`
function planHeader(ctx: CanvasRenderingContext2D, W: number, top: number, name: string, date: string) {
  const cx = W / 2;
  withShadow(ctx, () => {
    ctx.textAlign = "center";
    ctx.fillStyle = TEAL_LIGHT; ctx.font = `800 42px ${CANVAS_FONT}`;
    outlinedText(ctx, "PLANO × FEITO", cx, top + 50, 6);
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 66px ${CANVAS_FONT}`;
    outlinedText(ctx, fitText(ctx, name, W - 160), cx, top + 135, 8);
    ctx.font = `700 34px ${CANVAS_FONT}`; ctx.fillStyle = "rgba(255,255,255,0.9)";
    outlinedText(ctx, date, cx, top + 190, 4);
  });
}

// TIROS — uma barra por tiro (mais rápido = mais alta), faixa do alvo por trás,
// cor por tiro (no alvo / rápido demais / lento)
function drawTiros(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras, ph: PlanPhase) {
  const cx = W / 2, left = 110, right = W - 110;
  const top = 90;
  planHeader(ctx, W, top, x.planned?.workout_type ?? "", x.date);

  withShadow(ctx, () => {
    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF"; ctx.font = `800 46px ${CANVAS_FONT}`;
    outlinedText(ctx, ph.target ? `${ph.label} · alvo ${ph.target}` : ph.label, cx, top + 290, 6);
  });

  // escala de ritmo: rápido em cima. Folga pra faixa do alvo e os extremos
  const paces = ph.reps.map((r) => r.pace_sec).filter((v): v is number => v != null);
  const lo = ph.target_min_sec, hi = ph.target_max_sec ?? lo;
  const fast = Math.min(...paces, lo != null ? lo * (1 - PACE_SLACK) : Infinity) - 12;
  const slow = Math.max(...paces, hi != null ? hi * (1 + PACE_SLACK) : -Infinity) + 25;
  const cTop = top + 370, cBot = top + 790;
  const yOf = (sec: number) => cTop + ((sec - fast) / (slow - fast)) * (cBot - cTop);

  // faixa do alvo — com a MESMA folga de ruído de GPS que o veredito usa
  // (3%), senão tiro "no alvo" apareceria fora da faixa
  if (lo != null && hi != null) {
    const y1 = yOf(lo * (1 - PACE_SLACK)), y2 = yOf(hi * (1 + PACE_SLACK));
    ctx.fillStyle = "rgba(52,227,200,0.16)";
    ctx.fillRect(left - 10, y1, right - left + 20, Math.max(6, y2 - y1));
    ctx.strokeStyle = "rgba(52,227,200,0.6)"; ctx.lineWidth = 2; ctx.setLineDash([10, 8]);
    ctx.beginPath(); ctx.moveTo(left - 10, y1); ctx.lineTo(right + 10, y1); ctx.moveTo(left - 10, y2); ctx.lineTo(right + 10, y2); ctx.stroke();
    ctx.setLineDash([]);
  }

  const n = ph.reps.length;
  const gap = n > 12 ? 8 : 18;
  const bw = (right - left - gap * (n - 1)) / n;
  const showVals = n <= 10;
  ph.reps.forEach((r, i) => {
    const bx = left + i * (bw + gap);
    const yTop = r.pace_sec != null ? yOf(r.pace_sec) : cBot - 10;
    const h = Math.max(10, cBot - yTop);
    withShadow(ctx, () => {
      ctx.fillStyle = repColor(r.pace_sec, r.ok, lo);
      roundRect(ctx, bx, cBot - h, bw, h, Math.min(12, bw / 2)); ctx.fill();
    });
    ctx.textAlign = "center"; ctx.fillStyle = "#FFFFFF";
    if (showVals && r.pace_sec != null) {
      ctx.font = `800 ${bw > 80 ? 32 : 26}px ${CANVAS_FONT}`;
      outlinedText(ctx, fmtPaceSec(r.pace_sec), bx + bw / 2, cBot - h - 14, 4);
    }
    if (n <= 16 || i % 2 === 0) {
      ctx.font = `800 30px ${CANVAS_FONT}`;
      outlinedText(ctx, String(i + 1), bx + bw / 2, cBot + 44, 4);
    }
  });

  const statsEnd = drawStatsSpread(ctx, left, right, cBot + 140, [
    ["No alvo", `${ph.ok}/${ph.total}`],
    ["Média dos tiros", fmtPaceSec(ph.avg_pace_sec)],
    ["Distância", `${km2(it.distance_km)} km`],
  ], 60, 38);
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(statsEnd + 100, H - 40), 46, true));
}

// BLOCOS — uma linha por trecho do plano (10 km leve, 4 km forte…): alvo ×
// feito com ✓/✗
function drawBlocos(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras, phases: PlanPhase[]) {
  const cx = W / 2, left = 110;
  const colP = 560, colF = 820;
  const rowH = 130;
  const okCount = phases.filter((ph) => ph.ok === ph.total).length;
  const blockH = 300 + (phases.length + 1) * rowH + 130 + 130;
  const top = Math.max(60, (H - blockH) / 2);
  planHeader(ctx, W, top, x.planned?.workout_type ?? "", x.date);

  let y = top + 300;
  withShadow(ctx, () => {
    ctx.textAlign = "center"; ctx.font = `800 32px ${CANVAS_FONT}`;
    ctx.fillStyle = "rgba(255,255,255,0.8)"; outlinedText(ctx, "ALVO", colP, y, 4);
    ctx.fillStyle = TEAL_LIGHT; outlinedText(ctx, "FEITO", colF, y, 4);
  });
  y += 40;
  const line = (yy: number) => { ctx.fillStyle = "rgba(255,255,255,0.28)"; ctx.fillRect(left, yy, W - 2 * left, 3); };
  for (const ph of phases) {
    line(y);
    const base = y + 88;
    const allOk = ph.ok === ph.total;
    withShadow(ctx, () => {
      ctx.textAlign = "left"; ctx.fillStyle = "#FFFFFF"; ctx.font = `800 42px ${CANVAS_FONT}`;
      outlinedText(ctx, ph.label, left, base - 6, 5);
      ctx.textAlign = "center"; ctx.font = `700 46px ${CANVAS_FONT}`; ctx.fillStyle = "rgba(255,255,255,0.85)";
      outlinedText(ctx, ph.target ?? "livre", colP, base, 6);
      ctx.font = `800 56px ${CANVAS_FONT}`; ctx.fillStyle = "#FFFFFF";
      outlinedText(ctx, fmtPaceSec(ph.avg_pace_sec), colF, base, 7);
      // ✓ / ✗ (parcial = "2/3")
      ctx.textAlign = "left"; ctx.font = `800 44px ${CANVAS_FONT}`;
      ctx.fillStyle = allOk ? OK_COLOR : FAST_COLOR;
      outlinedText(ctx, allOk ? "✓" : (ph.total > 1 ? `${ph.ok}/${ph.total}` : "✗"), colF + 100, base, 5);
    });
    y += rowH;
  }
  // total do treino
  line(y);
  withShadow(ctx, () => {
    ctx.textAlign = "left"; ctx.fillStyle = "#FFFFFF"; ctx.font = `700 38px ${CANVAS_FONT}`;
    outlinedText(ctx, "Total", left, y + 80, 5);
    const pd = x.planned?.distance_km;
    ctx.textAlign = "center"; ctx.font = `700 46px ${CANVAS_FONT}`; ctx.fillStyle = "rgba(255,255,255,0.85)";
    outlinedText(ctx, pd ? `${km1(pd)} km` : "—", colP, y + 86, 6);
    ctx.font = `800 52px ${CANVAS_FONT}`; ctx.fillStyle = "#FFFFFF";
    outlinedText(ctx, `${km2(it.distance_km)} km`, colF, y + 86, 7);
  });
  y += rowH;
  line(y);

  const verdict = okCount === phases.length
    ? `✅ ${phases.length === 1 ? "Bloco" : `Os ${phases.length} blocos`} no alvo`
    : `${okCount} de ${phases.length} blocos no alvo`;
  drawPill(ctx, cx, y + 110, verdict, 40, TEAL_LIGHT);
  withShadow(ctx, () => drawBrand(ctx, cx, Math.min(y + 240, H - 40), 46, true));
}

// PLANO × FEITO — o que o coach passou lado a lado com o que o atleta fez.
// Treino estruturado COM as voltas do relógio: tiros viram gráfico tiro a
// tiro; blocos (progressivo) viram uma linha por bloco. Senão, tabela simples.
export function drawPlanoFeito(ctx: CanvasRenderingContext2D, W: number, H: number, it: FeedItem, x: RunExtras) {
  const p = x.planned;
  const cx = W / 2, left = 110;
  const colP = 560, colF = 830;
  if (!p) return;

  const phases = p.phases ?? [];
  const tiros = phases.find((ph) => ph.kind === "tiros" && ph.total >= 2);
  if (tiros) { drawTiros(ctx, W, H, it, x, tiros); return; }
  if (p.pace_structured && phases.length) { drawBlocos(ctx, W, H, it, x, phases); return; }

  const plannedPace = p.pace_label
    || (p.pace_min && p.pace_max && p.pace_min !== p.pace_max
      ? `${p.pace_min}–${p.pace_max}` : (p.pace_min || p.pace_max || null));
  // distância e ritmo sempre (o que o plano não fixou: "livre"/"por tempo"); tempo
  // só quando o plano é por tempo
  const rows: [string, string, string][] = [];
  // sessão por TEMPO não tem distância prescrita: "por tempo" (não "livre")
  rows.push(["Distância", p.distance_km ? `${km1(p.distance_km)} km` : (p.duration_min ? "por tempo" : "livre"), `${km2(it.distance_km)} km`]);
  if (p.duration_min) rows.push(["Tempo", durShort(p.duration_min * 60), durShort(durOf(it))]);
  // estruturado sem as voltas do relógio: sem linha de ritmo (a média de um
  // fartlek/progressivo mistura blocos e não diz nada)
  if (!p.pace_structured) rows.push(["Ritmo", plannedPace ?? "livre", it.pace ?? "—"]);
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
      const soft = pv === "livre" || pv === "por tempo";
      ctx.fillStyle = soft ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.85)";
      if (soft) {
        ctx.font = `italic 700 42px ${CANVAS_FONT}`;
      } else {
        // planejado encolhe até caber entre o rótulo e a coluna do feito
        // ("6:20–6:45 → 5:25–5:40" é longo)
        const maxP = 2 * Math.min(colP - (left + 190), colF - 130 - colP);
        const fit = (txt: string, from: number, min: number) => {
          let ps = from;
          ctx.font = `700 ${ps}px ${CANVAS_FONT}`;
          while (ctx.measureText(txt).width > maxP && ps > min) { ps -= 2; ctx.font = `700 ${ps}px ${CANVAS_FONT}`; }
          return ctx.measureText(txt).width <= maxP;
        };
        // estrutura longa ("A → B"): em duas linhas, quebrando na seta
        const parts = pv.split(/ (?=→ )| \/ /);
        if (!fit(pv, 50, 36) && parts.length === 2) {
          const [l1, l2] = parts;
          fit(l1.length > l2.length ? l1 : l2, 40, 26);
          outlinedText(ctx, l1, colP, base - 26, 5);
          outlinedText(ctx, l2, colP, base + 20, 5);
        } else {
          fit(pv, 50, 26);
          outlinedText(ctx, pv, colP, base, 6);
        }
      }
      if (soft) outlinedText(ctx, pv, colP, base, 6);
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
