// Desenho dos cards de COMPARTILHAR (canvas 1080×1350) — peças comuns aos
// cards de corrida (/atividades) e de resumo semanal/mensal (/evolucao):
// marca Ritmind, texto com contorno, fundo/scrims, linha de dados e o
// compartilhar/copiar do PNG. Uma fonte só pra todos os cards ficarem com a
// mesma cara.

export const CARD_W = 1080;
export const CARD_H = 1350;

// cantinho arredondado — sem depender de ctx.roundRect (suporte irregular em
// PWA/iOS mais antigo); usado só pela trilha/barra do estilo Parciais.
export function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, h / 2, Math.max(w, 0) / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

export function drawBg(ctx: CanvasRenderingContext2D, W: number, H: number, photo: HTMLImageElement | null, mapCard: HTMLCanvasElement | null) {
  if (photo && photo.width) {
    const s = Math.max(W / photo.width, H / photo.height);
    const dw = photo.width * s, dh = photo.height * s;
    ctx.drawImage(photo, (W - dw) / 2, (H - dh) / 2, dw, dh);
  } else if (mapCard) {
    ctx.drawImage(mapCard, 0, 0, W, H);
  } else {
    ctx.fillStyle = "#0C0D16"; ctx.fillRect(0, 0, W, H);
  }
}

export function topScrim(ctx: CanvasRenderingContext2D, W: number) {
  const g = ctx.createLinearGradient(0, 0, 0, 240);
  g.addColorStop(0, "rgba(6,7,12,0.72)"); g.addColorStop(1, "rgba(6,7,12,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 240);
}

export function bottomScrim(ctx: CanvasRenderingContext2D, W: number, H: number, fromY: number) {
  const g = ctx.createLinearGradient(0, fromY, 0, H);
  g.addColorStop(0, "rgba(6,7,12,0)"); g.addColorStop(0.55, "rgba(6,7,12,0.78)"); g.addColorStop(1, "rgba(6,7,12,0.96)");
  ctx.fillStyle = g; ctx.fillRect(0, fromY, W, H - fromY);
}

// família usada no canvas do card de compartilhar: Inter (grotesca neutra e
// limpa, estilo Strava), via next/font (--font-share). Resolvida do CSS em
// runtime; fallback pra Archivo/system se não carregar.
export let CANVAS_FONT = "system-ui, sans-serif";   // Inter (stats)
export let BRAND_FONT = "system-ui, sans-serif";    // Space Grotesk (wordmark Ritmind)
export function refreshCanvasFont() {
  if (typeof window === "undefined") return;
  const cs = getComputedStyle(document.body);
  const share = cs.getPropertyValue("--font-share").trim();
  const disp = cs.getPropertyValue("--font-display").trim();
  const brand = cs.getPropertyValue("--font-brand").trim();
  if (share || disp) CANVAS_FONT = `${share || disp}, system-ui, sans-serif`;
  if (brand || disp) BRAND_FONT = `${brand || disp}, system-ui, sans-serif`;
}

// o "pulso" do ícone do app (path M2 12h4l2.5-7 4 15 2.5-8H22 da marca),
// desenhado a partir de (x, y) = começo da linha, na escala `sx` (e `sy`)
export function drawPulse(ctx: CanvasRenderingContext2D, x: number, y: number, sx: number, color: string, lw: number, sy = sx) {
  const P = [[2, 12], [6, 12], [8.5, 5], [12.5, 20], [15, 12], [22, 12]];
  ctx.save();
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.strokeStyle = color; ctx.lineWidth = lw;
  ctx.beginPath();
  P.forEach(([px, py], i) => {
    const X = x + (px - 2) * sx, Y = y + (py - 12) * sy;
    if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
  });
  ctx.stroke();
  ctx.restore();
}

// marca dos cards = SELO: pílula teal com o pulso do app + "ritmind" escuro
// (escolha do Renato, 2026-09-26 — a palavra solta "Ritmind" era "comum
// demais"). Mesma assinatura de antes: `baseY` ≈ linha de base do texto,
// `center=true` centraliza em x, senão a pílula começa em x.
export function drawBrand(ctx: CanvasRenderingContext2D, x: number, baseY: number, size: number, center: boolean) {
  const s = Math.round(size * 1.25);
  const fs = Math.round(s * 0.8);
  ctx.font = `800 ${fs}px ${BRAND_FONT}`;
  const tw = ctx.measureText("ritmind").width;
  const ic = s * 0.62, gap = s * 0.2, padX = s * 0.45, h = s * 1.25;
  const w = padX * 2 + ic + gap + tw;
  const left = center ? x - w / 2 : x;
  // pílula ocupa ~o mesmo vão vertical que a palavra antiga ocupava (não
  // encosta na linha de dados de cima)
  const top = baseY - s * 0.15 - h / 2;
  ctx.fillStyle = "#34E3C8";
  roundRect(ctx, left, top, w, h, h / 2); ctx.fill();
  // o que vem depois (pulso/texto) sem a sombra do chamador
  ctx.save();
  ctx.shadowColor = "transparent";
  drawPulse(ctx, left + padX, top + h / 2, ic / 20, "#06201B", s * 0.085);
  ctx.fillStyle = "#06201B"; ctx.textAlign = "left";
  ctx.fillText("ritmind", left + padX + ic + gap, top + h * 0.7);
  ctx.restore();
}

// sombra suave: deixa texto/rota legíveis sobre QUALQUER foto (o card é
// transparente e vai ser colado por cima da foto do atleta no Instagram).
export function withShadow(ctx: CanvasRenderingContext2D, fn: () => void) {
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 16; ctx.shadowOffsetY = 2;
  fn();
  ctx.restore();
}

// texto com CONTORNO escuro (não só sombra difusa) — a mesma ideia do traçado
// da rota (drawRouteBox: stroke escuro por baixo, cor por cima), aplicada a
// texto: segura contraste em QUALQUER foto. Padrão em TODOS os estilos de
// compartilhar (pedido do Renato: padronizar o tratamento de texto).
export function outlinedText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, lineW: number) {
  ctx.lineJoin = "round";
  ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.lineWidth = lineW;
  ctx.strokeText(text, x, y);
  ctx.fillText(text, x, y);
}

// tempo tipo Strava: "53min 24s" (ou "1h05" em corrida longa)
export function fmtDur(s: number): string {
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}`;
  return ss > 0 ? `${m}min ${ss}s` : `${m}min`;
}

// linha de dados JUSTIFICADA na largura de um bloco [left, right] (1ª coluna
// alinhada à esquerda, última à direita, meio centralizado no vão) — encolhe a
// fonte até caber, pra acompanhar exatamente a largura das barras/bloco.
export function drawStatsSpread(
  ctx: CanvasRenderingContext2D, left: number, right: number, baseY: number,
  cells: [string, string][], valStart = 54, labStart = 32,
): number {
  const blockW = right - left, minGap = 28;
  const ratio = labStart / valStart;
  let valSize = valStart, labSize = labStart;
  let widths: number[] = [];
  const measure = () => {
    widths = cells.map(([lab, val]) => {
      ctx.font = `800 ${valSize}px ${CANVAS_FONT}`; const wv = ctx.measureText(val).width;
      ctx.font = `700 ${labSize}px ${CANVAS_FONT}`; const wl = ctx.measureText(lab).width;
      return Math.max(wv, wl);
    });
    return widths.reduce((a, b) => a + b, 0) + minGap * (cells.length - 1);
  };
  while (measure() > blockW && valSize > 30) { valSize -= 2; labSize = Math.round(valSize * ratio); }
  const free = blockW - widths.reduce((a, b) => a + b, 0);
  const gap = cells.length > 1 ? free / (cells.length - 1) : 0;
  let cx = left;
  withShadow(ctx, () => {
    ctx.textAlign = "left";
    cells.forEach(([lab, val], i) => {
      ctx.fillStyle = "#FFFFFF"; ctx.font = `700 ${labSize}px ${CANVAS_FONT}`;
      outlinedText(ctx, lab, cx, baseY, Math.max(3, labSize * 0.11));
      ctx.font = `800 ${valSize}px ${CANVAS_FONT}`;
      outlinedText(ctx, val, cx, baseY + valSize + 8, Math.max(3, valSize * 0.11));
      cx += widths[i] + gap;
    });
  });
  return baseY + valSize + 8; // baseline do valor (pra posicionar a marca)
}

// garante as fontes do card (Inter + Space Grotesk + pesos extras dos modelos)
// antes de pintar — o canvas cai no fallback se desenhar antes. Pinta já e
// repinta quando carregarem. Devolve um CANCELADOR: o useEffect chama na troca
// de modelo/fundo, senão a repintura agendada do modelo ANTERIOR chega depois
// (fonte ainda carregando) e pinta o card velho por cima do novo — o bug do
// "fundo preso" ao trocar de modelo.
export function paintWhenFontsReady(paint: () => void): () => void {
  let alive = true;
  const run = () => { if (alive) paint(); };
  refreshCanvasFont();
  run();
  const fam = CANVAS_FONT.split(",")[0].trim();
  const brand = BRAND_FONT.split(",")[0].trim();
  if (typeof document === "undefined" || !document.fonts || !fam) return () => { alive = false; };
  Promise.all([
    document.fonts.load(`800 100px ${fam}`),
    document.fonts.load(`900 100px ${fam}`),
    document.fonts.load(`700 40px ${fam}`),
    document.fonts.load(`italic 700 40px ${fam}`),
    document.fonts.load(`700 48px ${brand}`),
  ]).then(run).catch(() => {});
  document.fonts.ready.then(run).catch(() => {});
  return () => { alive = false; };
}

export function canvasBlob(cv: HTMLCanvasElement | null): Promise<Blob | null> {
  if (!cv) return Promise.resolve(null);
  return new Promise((res) => cv.toBlob((b) => res(b), "image/png"));
}

// copia o PNG pro clipboard (colar direto no story). false = sem suporte.
export async function copyBlob(blob: Blob): Promise<boolean> {
  const CI = (window as unknown as { ClipboardItem?: typeof ClipboardItem }).ClipboardItem;
  if (!navigator.clipboard || !CI) return false;
  try {
    await navigator.clipboard.write([new CI({ "image/png": blob })]);
    return true;
  } catch {
    return false;
  }
}

// share nativo com arquivo. "shared" | "aborted" | "unsupported" (aí o
// chamador mostra a imagem pra salvar/baixar).
export async function shareBlob(blob: Blob, filename: string, text: string): Promise<"shared" | "aborted" | "unsupported"> {
  const file = new File([blob], filename, { type: "image/png" });
  const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
  if (!(navShare.canShare && navShare.canShare({ files: [file] }))) return "unsupported";
  try {
    await navigator.share({ files: [file], text });
    return "shared";
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return "aborted";
    return "unsupported";
  }
}

// quebra `text` em linhas que cabem em maxW (fonte já setada no ctx); corta com
// "…" se passar de maxLines
export function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(next).width <= maxW || !cur) { cur = next; continue; }
    lines.push(cur); cur = w;
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    let last = kept[maxLines - 1];
    while (last && ctx.measureText(`${last}…`).width > maxW) last = last.slice(0, -1);
    kept[maxLines - 1] = `${last.trimEnd()}…`;
    return kept;
  }
  return lines;
}

// corta um texto de UMA linha pra caber em maxW (com "…")
export function fitText(ctx: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (ctx.measureText(text).width <= maxW) return text;
  let t = text;
  while (t && ctx.measureText(`${t}…`).width > maxW) t = t.slice(0, -1);
  return `${t.trimEnd()}…`;
}

// wordmark pra fundo CLARO (papel do número de peito): "Rit" teal
// escuro + "mind" quase preto, sem contorno
export function drawBrandOnLight(ctx: CanvasRenderingContext2D, x: number, baseY: number, size: number, center: boolean) {
  const s = Math.round(size * 1.15);
  ctx.font = `700 ${s}px ${BRAND_FONT}`;
  const wRit = ctx.measureText("Rit").width, wMind = ctx.measureText("mind").width;
  const startX = center ? x - (wRit + wMind) / 2 : x;
  ctx.textAlign = "left";
  ctx.fillStyle = "#0E9C85"; ctx.fillText("Rit", startX, baseY);
  ctx.fillStyle = "#15161C"; ctx.fillText("mind", startX + wRit, baseY);
}

// selo/pílula centralizado em cx com texto (veredito do Plano × feito etc.)
export function drawPill(ctx: CanvasRenderingContext2D, cx: number, baseY: number, text: string, size: number, color: string) {
  ctx.font = `800 ${size}px ${CANVAS_FONT}`;
  const w = ctx.measureText(text).width + size * 1.4, h = size * 1.9;
  const x = cx - w / 2, y = baseY - size * 1.28;
  withShadow(ctx, () => {
    ctx.fillStyle = "rgba(6,7,12,0.55)";
    roundRect(ctx, x, y, w, h, h / 2); ctx.fill();
  });
  ctx.lineWidth = 4; ctx.strokeStyle = color;
  roundRect(ctx, x, y, w, h, h / 2); ctx.stroke();
  ctx.fillStyle = color; ctx.textAlign = "center";
  ctx.fillText(text, cx, baseY);
  ctx.textAlign = "left";
}

// fundo da versão "Card" de QUALQUER modelo (corrida e resumo): foto do atleta
// ou mapa real da corrida (escurecidos pra leitura) ou, sem nenhum, escuro com
// brilho teal suave (não fica chapado)
export function drawCardBackground(
  ctx: CanvasRenderingContext2D, W: number, H: number,
  photo: HTMLImageElement | null, mapCard: HTMLCanvasElement | null,
) {
  drawBg(ctx, W, H, photo, mapCard);
  if (photo || mapCard) {
    ctx.fillStyle = "rgba(6,7,12,0.28)"; ctx.fillRect(0, 0, W, H);
    topScrim(ctx, W); bottomScrim(ctx, W, H, Math.round(H * 0.28));
    return;
  }
  const gy = Math.min(520, H / 2);
  const g = ctx.createRadialGradient(W / 2, gy, 40, W / 2, gy, Math.max(W, H) * 0.7);
  g.addColorStop(0, "rgba(31,217,184,0.20)"); g.addColorStop(1, "rgba(31,217,184,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
}
