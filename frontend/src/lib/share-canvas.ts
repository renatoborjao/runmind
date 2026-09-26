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

// wordmark "Ritmind" — "Rit" na cor da marca (teal) + "mind" branco, na fonte
// descolada (Space Grotesk). `center=true` centraliza em x. Leve aumento +
// contorno escuro (pedido do Renato: "dar mais vida") — mesma técnica de
// contraste do resto do card (outlinedText), aplicada às duas cores do wordmark.
export function drawBrand(ctx: CanvasRenderingContext2D, x: number, baseY: number, size: number, center: boolean) {
  const s = Math.round(size * 1.15);
  ctx.font = `700 ${s}px ${BRAND_FONT}`;
  ctx.lineJoin = "round";
  const wRit = ctx.measureText("Rit").width, wMind = ctx.measureText("mind").width;
  const startX = center ? x - (wRit + wMind) / 2 : x;
  ctx.textAlign = "left";
  ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.lineWidth = Math.max(3, s * 0.1);
  ctx.strokeText("Rit", startX, baseY); ctx.strokeText("mind", startX + wRit, baseY);
  ctx.fillStyle = "#34E3C8"; ctx.fillText("Rit", startX, baseY);
  ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", startX + wRit, baseY);
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
  cells: [string, string][],
): number {
  const blockW = right - left, minGap = 28;
  let valSize = 54, labSize = 32;
  let widths: number[] = [];
  const measure = () => {
    widths = cells.map(([lab, val]) => {
      ctx.font = `800 ${valSize}px ${CANVAS_FONT}`; const wv = ctx.measureText(val).width;
      ctx.font = `700 ${labSize}px ${CANVAS_FONT}`; const wl = ctx.measureText(lab).width;
      return Math.max(wv, wl);
    });
    return widths.reduce((a, b) => a + b, 0) + minGap * (cells.length - 1);
  };
  while (measure() > blockW && valSize > 30) { valSize -= 2; labSize = Math.round(valSize * 0.6); }
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

// garante as fontes do card (Inter + Space Grotesk) antes de pintar — o canvas
// cai no fallback se desenhar antes. Pinta já e repinta quando carregarem.
export function paintWhenFontsReady(paint: () => void) {
  refreshCanvasFont();
  paint();
  const fam = CANVAS_FONT.split(",")[0].trim();
  const brand = BRAND_FONT.split(",")[0].trim();
  if (typeof document === "undefined" || !document.fonts || !fam) return;
  Promise.all([
    document.fonts.load(`800 100px ${fam}`),
    document.fonts.load(`700 40px ${fam}`),
    document.fonts.load(`700 48px ${brand}`),
  ]).then(paint).catch(() => {});
  document.fonts.ready.then(paint).catch(() => {});
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
