"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  deleteActivityPhoto,
  getActivityAnalysis,
  getActivityPhoto,
  getFeed,
  getTrack,
  setActivityTitle,
  uploadActivityPhoto,
  type CoachAnalysis,
  type FeedItem,
  type RunSplit,
  type TrackData,
} from "@/lib/api";
import { ActivityDetailBody, CommentsSection, fmtDate, fmtTime, km, RouteThumb } from "../activity-detail";

// Leaflet carregado sob demanda dentro do card compartilhável (mapa REAL de
// fundo). O detalhe da atividade (mapa herói + stats + splits) vive no
// componente compartilhado ActivityDetailBody.
declare global { interface Window { L?: any } }

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

// ---- mapa REAL de fundo (estilo Strava): tiles escuros do CARTO (grátis, com
// CORS -> canvas exportável) + a rota por cima, renderizados num canvas offscreen ----
function _lon2x(lon: number, z: number) { return ((lon + 180) / 360) * 256 * Math.pow(2, z); }
function _lat2y(lat: number, z: number) {
  const r = (lat * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 256 * Math.pow(2, z);
}
function _tileURL(z: number, x: number, y: number) {
  const subs = ["a", "b", "c", "d"];
  return `https://${subs[(x + y) % subs.length]}.basemaps.cartocdn.com/dark_all/${z}/${x}/${y}.png`;
}
function _loadTile(url: string): Promise<HTMLImageElement | null> {
  return new Promise((res) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => res(img);
    img.onerror = () => res(null);
    img.src = url;
  });
}
async function buildMapCard(points: { lat: number; lon: number }[], W: number, H: number): Promise<HTMLCanvasElement | null> {
  const good = points.filter((p) => p.lat && p.lon);
  if (good.length < 2) return null;
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const padLa = (maxLa - minLa) * 0.16 || 0.003, padLo = (maxLo - minLo) * 0.16 || 0.003;
  minLa -= padLa; maxLa += padLa; minLo -= padLo; maxLo += padLo;
  let z = 17;
  for (; z >= 3; z--) {
    if (_lon2x(maxLo, z) - _lon2x(minLo, z) <= W && _lat2y(minLa, z) - _lat2y(maxLa, z) <= H) break;
  }
  const originX = (_lon2x(minLo, z) + _lon2x(maxLo, z)) / 2 - W / 2;
  const originY = (_lat2y(minLa, z) + _lat2y(maxLa, z)) / 2 - H / 2;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d"); if (!ctx) return null;
  ctx.fillStyle = "#11131C"; ctx.fillRect(0, 0, W, H);
  const maxT = Math.pow(2, z) - 1;
  const jobs: Promise<void>[] = [];
  for (let tx = Math.floor(originX / 256); tx <= Math.floor((originX + W) / 256); tx++) {
    for (let ty = Math.floor(originY / 256); ty <= Math.floor((originY + H) / 256); ty++) {
      if (ty < 0 || ty > maxT) continue;
      const gx = ((tx % (maxT + 1)) + (maxT + 1)) % (maxT + 1);
      const dx = tx * 256 - originX, dy = ty * 256 - originY;
      jobs.push(_loadTile(_tileURL(z, gx, ty)).then((img) => { if (img) ctx.drawImage(img, dx, dy, 256, 256); }));
    }
  }
  await Promise.all(jobs);
  ctx.save();
  ctx.shadowColor = "rgba(31,217,184,0.5)"; ctx.shadowBlur = 16;
  ctx.strokeStyle = "#1FD9B8"; ctx.lineWidth = 8; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  good.forEach((p, i) => { const x = _lon2x(p.lon, z) - originX, y = _lat2y(p.lat, z) - originY; if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  ctx.restore();
  return cv;
}

// ---- estilos de card compartilhável (foto OU mapa real de fundo) ----
interface CardData { it: FeedItem; pts: { lat: number; lon: number }[]; date: string; name: string; kmTxt: string; photo: HTMLImageElement | null; mapCard: HTMLCanvasElement | null; splits: RunSplit[]; }

// cantinho arredondado — sem depender de ctx.roundRect (suporte irregular em
// PWA/iOS mais antigo); usado só pela trilha/barra do estilo Parciais.
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, h / 2, Math.max(w, 0) / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawBg(ctx: CanvasRenderingContext2D, W: number, H: number, photo: HTMLImageElement | null, mapCard: HTMLCanvasElement | null) {
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
function topScrim(ctx: CanvasRenderingContext2D, W: number) {
  const g = ctx.createLinearGradient(0, 0, 0, 240);
  g.addColorStop(0, "rgba(6,7,12,0.72)"); g.addColorStop(1, "rgba(6,7,12,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 240);
}
function bottomScrim(ctx: CanvasRenderingContext2D, W: number, H: number, fromY: number) {
  const g = ctx.createLinearGradient(0, fromY, 0, H);
  g.addColorStop(0, "rgba(6,7,12,0)"); g.addColorStop(0.55, "rgba(6,7,12,0.78)"); g.addColorStop(1, "rgba(6,7,12,0.96)");
  ctx.fillStyle = g; ctx.fillRect(0, fromY, W, H - fromY);
}
// família usada no canvas do card de compartilhar: Inter (grotesca neutra e
// limpa, estilo Strava), via next/font (--font-share). Resolvida do CSS em
// runtime; fallback pra Archivo/system se não carregar.
let CANVAS_FONT = "system-ui, sans-serif";   // Inter (stats)
let BRAND_FONT = "system-ui, sans-serif";    // Space Grotesk (wordmark Ritmind)
function refreshCanvasFont() {
  if (typeof window === "undefined") return;
  const cs = getComputedStyle(document.body);
  const share = cs.getPropertyValue("--font-share").trim();
  const disp = cs.getPropertyValue("--font-display").trim();
  const brand = cs.getPropertyValue("--font-brand").trim();
  if (share || disp) CANVAS_FONT = `${share || disp}, system-ui, sans-serif`;
  if (brand || disp) BRAND_FONT = `${brand || disp}, system-ui, sans-serif`;
}

// wordmark "Ritmind" — "Rit" na cor da marca (teal) + "mind" branco, na fonte
// descolada (Space Grotesk). `center=true` centraliza em x.
function drawBrand(ctx: CanvasRenderingContext2D, x: number, baseY: number, size: number, center: boolean) {
  ctx.font = `700 ${size}px ${BRAND_FONT}`;
  const wRit = ctx.measureText("Rit").width, wMind = ctx.measureText("mind").width;
  const startX = center ? x - (wRit + wMind) / 2 : x;
  ctx.textAlign = "left";
  ctx.fillStyle = "#34E3C8"; ctx.fillText("Rit", startX, baseY);
  ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", startX + wRit, baseY);
}
// sombra suave: deixa texto/rota legíveis sobre QUALQUER foto (o card é
// transparente e vai ser colado por cima da foto do atleta no Instagram).
function withShadow(ctx: CanvasRenderingContext2D, fn: () => void) {
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 16; ctx.shadowOffsetY = 2;
  fn();
  ctx.restore();
}
// traçado dentro de uma caixa (fit + início/fim), com brilho — pra fundo transparente
function drawRouteBox(
  ctx: CanvasRenderingContext2D, pts: { lat: number; lon: number }[],
  bx: number, by: number, bw: number, bh: number, color: string, lw: number,
) {
  const good = pts.filter((p) => p.lat && p.lon);
  if (good.length < 2) return;
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const kx = Math.cos(((minLa + maxLa) / 2 * Math.PI) / 180);
  const spanLo = Math.max(1e-6, (maxLo - minLo) * kx), spanLa = Math.max(1e-6, maxLa - minLa);
  const scale = Math.min(bw / spanLo, bh / spanLa);
  const ox = bx + (bw - spanLo * scale) / 2, oy = by + (bh - spanLa * scale) / 2;
  const px = (p: { lat: number; lon: number }) => ox + (p.lon - minLo) * kx * scale;
  const py = (p: { lat: number; lon: number }) => oy + (maxLa - p.lat) * scale;
  ctx.save();
  // glow na cor do traçado (vida) + contorno escuro sutil pra legibilidade
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(0,0,0,0.5)"; ctx.lineWidth = lw + 4; ctx.shadowBlur = 0;
  ctx.beginPath();
  good.forEach((p, i) => { const x = px(p), y = py(p); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  ctx.shadowColor = color; ctx.shadowBlur = 10;
  ctx.strokeStyle = color; ctx.lineWidth = lw;
  ctx.beginPath();
  good.forEach((p, i) => { const x = px(p), y = py(p); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  ctx.restore();
}
function brandDate(ctx: CanvasRenderingContext2D, W: number, d: CardData) {
  withShadow(ctx, () => drawBrand(ctx, 64, 100, 42, false));
  ctx.font = `600 28px ${CANVAS_FONT}`; ctx.fillStyle = "#E7E8F0"; ctx.textAlign = "right";
  ctx.fillText(d.date, W - 64, 100); ctx.textAlign = "left";
}
function footer(ctx: CanvasRenderingContext2D, W: number, H: number) {
  ctx.fillStyle = "#9A9BAE"; ctx.font = `600 22px ${CANVAS_FONT}`; ctx.textAlign = "center";
  ctx.fillText("ritmind", W / 2, H - 34); ctx.textAlign = "left";
}

// tempo tipo Strava: "53min 24s" (ou "1h05" em corrida longa)
function fmtDur(s: number): string {
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}`;
  return ss > 0 ? `${m}min ${ss}s` : `${m}min`;
}
// [rótulo, valor com unidade] — Distância / Ritmo / Tempo (+ FC quando tem)
function shareCells(it: FeedItem): [string, string][] {
  const c: [string, string][] = [
    ["Distância", `${it.distance_km.toFixed(2).replace(".", ",")} km`],
    ["Ritmo", `${it.pace ?? "—"} /km`],
    ["Tempo", fmtDur(it.duration_s || it.duration_min * 60)],
  ];
  if (it.avg_hr != null) c.push(["FC média", `${it.avg_hr} bpm`]);
  return c;
}
// fileira de colunas (rótulo em cima, valor embaixo), largura automática;
// centerAt centraliza o conjunto num x. Sempre com sombra (fundo transparente).
function drawStatCols(
  ctx: CanvasRenderingContext2D, startX: number, baseY: number,
  cells: [string, string][], gap: number, valSize: number, labSize: number,
  centerAt?: number,
) {
  const widths = cells.map(([lab, val]) => {
    ctx.font = `800 ${valSize}px ${CANVAS_FONT}`; const wv = ctx.measureText(val).width;
    ctx.font = `600 ${labSize}px ${CANVAS_FONT}`; const wl = ctx.measureText(lab).width;
    return Math.max(wv, wl);
  });
  const total = widths.reduce((a, b) => a + b, 0) + gap * (cells.length - 1);
  let cx = centerAt != null ? centerAt - total / 2 : startX;
  withShadow(ctx, () => {
    ctx.textAlign = "left";
    cells.forEach(([lab, val], i) => {
      ctx.fillStyle = "#FFFFFF"; ctx.font = `700 ${labSize}px ${CANVAS_FONT}`;
      ctx.fillText(lab, cx, baseY);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 ${valSize}px ${CANVAS_FONT}`;
      ctx.fillText(val, cx, baseY + valSize + 10);
      cx += widths[i] + gap;
    });
  });
}

// ===== estilos TRANSPARENTES (PNG com fundo vazado) pra colar em cima da foto =====

// CENTRALIZADO — stats empilhados no centro + traçado pequeno + marca (template 1).
function styleCentralizado(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  const cx = W / 2;
  const cells = shareCells(d.it).slice(0, 3);
  let y = 360;
  withShadow(ctx, () => {
    ctx.textAlign = "center";
    for (const [lab, val] of cells) {
      ctx.fillStyle = "#FFFFFF"; ctx.font = `700 46px ${CANVAS_FONT}`; ctx.fillText(lab, cx, y);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 96px ${CANVAS_FONT}`; ctx.fillText(val, cx, y + 100);
      y += 186;
    }
    ctx.textAlign = "left";
  });
  if (d.pts.length >= 2) drawRouteBox(ctx, d.pts, cx - 150, y - 6, 300, 220, "#1FD9B8", 8);
  withShadow(ctx, () => drawBrand(ctx, cx, y + 296, 46, true));
}

// ROTA — traçado grande como herói + marca + stats embaixo (template 2).
function styleRota(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  const cx = W / 2;
  if (d.pts.length >= 2) drawRouteBox(ctx, d.pts, 110, 250, W - 220, 620, "#1FD9B8", 13);
  withShadow(ctx, () => drawBrand(ctx, cx, 980, 50, true));
  drawStatCols(ctx, 0, 1030, shareCells(d.it).slice(0, 3), 72, 58, 40, cx);
}

// CANTINHO — marca + stats no canto inferior esquerdo (template 3).
function styleCantinho(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  withShadow(ctx, () => drawBrand(ctx, 64, H - 230, 46, false));
  // layout original (horizontal); só o TÍTULO (rótulo) aumentado — era o que
  // ficava pequeno. Valor mantido no tamanho de antes.
  drawStatCols(ctx, 64, H - 150, shareCells(d.it).slice(0, 3), 64, 60, 40);
}

// COM MAPA — card completo (não transparente): mapa/foto de fundo + stats.
function styleMapa(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo, d.mapCard);
  topScrim(ctx, W); bottomScrim(ctx, W, H, H - 420);
  brandDate(ctx, W, d);
  drawStatCols(ctx, 64, H - 200, shareCells(d.it).slice(0, 3), 56, 72, 36);
  footer(ctx, W, H);
}

// texto com CONTORNO escuro (não só sombra difusa) — a mesma ideia do traçado
// da rota (drawRouteBox: stroke escuro por baixo, cor por cima), aplicada a
// texto: segura contraste em QUALQUER foto sem precisar de painel de fundo.
function outlinedText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, lineW: number) {
  ctx.lineJoin = "round";
  ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.lineWidth = lineW;
  ctx.strokeText(text, x, y);
  ctx.fillText(text, x, y);
}

// PARCIAIS — barra por km (mais rápido = barra maior), estilo Strava (template 5).
// Nada de painel de fundo (destoava, "não parece flutuar" — feedback do
// Renato): contraste vem de contorno no texto + barra com trilho escuro
// (halo), igual ao traçado da rota. Também mais estreito/baixo que a v1 —
// não precisa ocupar o card inteiro pra ser legível.
function styleParciais(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  const splits = d.splits.filter((s) => s.sec > 0);
  const titleY = 200;
  const labelX = 90, barX = 172, valueX = Math.round(W * 0.62);

  withShadow(ctx, () => {
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 44px ${CANVAS_FONT}`; ctx.textAlign = "left";
    outlinedText(ctx, "Parciais por KM", labelX, titleY, 7);
  });

  if (!splits.length) {
    withShadow(ctx, () => {
      ctx.fillStyle = "#E7E8F0"; ctx.font = `600 30px ${CANVAS_FONT}`;
      outlinedText(ctx, "Sem parciais nesta corrida", labelX, 250, 5);
    });
    withShadow(ctx, () => drawBrand(ctx, W / 2, 330, 40, true));
    return;
  }

  // compacto de verdade — não estica até o rodapé nem ocupa a largura toda;
  // encolhe mais ainda quando a corrida é longa (14+ splits).
  const top = 244;
  const rowH = Math.max(20, Math.min(46, 460 / splits.length));
  const barH = Math.max(9, Math.min(18, rowH * 0.4));
  const barMaxW = valueX - 130 - barX;

  const listBottom = top + splits.length * rowH;
  const brandY = Math.min(listBottom + 56, H - 90);

  const paceOf = (s: RunSplit) => s.sec / (s.partial_km || 1);
  const speeds = splits.map((s) => 1 / paceOf(s));
  const minSp = Math.min(...speeds), maxSp = Math.max(...speeds);
  const span = maxSp - minSp || 1;
  const minBarW = barMaxW * 0.14;

  splits.forEach((s, i) => {
    const y = top + i * rowH + rowH / 2;
    const barY = y - barH / 2;
    const w = Math.max(barH, minBarW + (barMaxW - minBarW) * ((1 / paceOf(s) - minSp) / span));
    const label = s.km != null ? String(s.km) : (s.partial_km != null ? String(s.partial_km).replace(".", ",") : "");

    withShadow(ctx, () => {
      // trilho: halo escuro por baixo (contraste em foto clara) + faixa sutil
      ctx.fillStyle = "rgba(0,0,0,0.4)";
      roundRect(ctx, barX - 2, barY - 2, barMaxW + 4, barH + 4, barH / 2 + 2); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.18)";
      roundRect(ctx, barX, barY, barMaxW, barH, barH / 2); ctx.fill();
      const grad = ctx.createLinearGradient(barX, 0, barX + w, 0);
      grad.addColorStop(0, "#1FD9B8"); grad.addColorStop(1, "#34E3C8");
      ctx.fillStyle = grad;
      roundRect(ctx, barX, barY, w, barH, barH / 2); ctx.fill();
    });

    ctx.fillStyle = "#FFFFFF"; ctx.font = `700 ${Math.round(rowH * 0.42)}px ${CANVAS_FONT}`; ctx.textAlign = "left";
    outlinedText(ctx, label, labelX, y + rowH * 0.15, 4);

    ctx.font = `600 ${Math.round(rowH * 0.36)}px ${CANVAS_FONT}`; ctx.textAlign = "right";
    outlinedText(ctx, s.pace ?? "—", valueX, y + rowH * 0.13, 4);
    ctx.textAlign = "left";
  });

  // marca colada logo abaixo da última linha
  withShadow(ctx, () => drawBrand(ctx, W / 2, brandY, 40, true));
}

interface CardStyle { key: string; label: string; transparent: boolean; draw: (c: CanvasRenderingContext2D, W: number, H: number, d: CardData) => void; }
const CARD_STYLES: CardStyle[] = [
  { key: "centralizado", label: "Central", transparent: true, draw: styleCentralizado },
  { key: "rota", label: "Rota", transparent: true, draw: styleRota },
  { key: "cantinho", label: "Cantinho", transparent: true, draw: styleCantinho },
  { key: "parciais", label: "Parciais", transparent: true, draw: styleParciais },
  { key: "mapa", label: "Com mapa", transparent: false, draw: styleMapa },
];

function AtividadesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<FeedItem | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [analysis, setAnalysis] = useState<CoachAnalysis | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [editor, setEditor] = useState(false);
  const [photoImg, setPhotoImg] = useState<HTMLImageElement | null>(null);
  const [styleIdx, setStyleIdx] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mapCard, setMapCard] = useState<HTMLCanvasElement | null>(null);
  // adornos da atividade (título custom + foto), só na MINHA tela
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [metaOpen, setMetaOpen] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const metaFileRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    (async () => {
      // Alvo do deep-link, consumido UMA vez ANTES do feed. No export estático do
      // Next a query da URL não chega de forma confiável na navegação client-side
      // (só no reload) — por isso a home grava a data no sessionStorage ANTES de
      // navegar (gatilho síncrono e confiável). A URL (?date=/?key=) fica como
      // fallback pra refresh/deep-link direto.
      let date: string | null = null;
      let key: string | null = null;
      try {
        date = sessionStorage.getItem("rm_open_activity_date");
        if (date) sessionStorage.removeItem("rm_open_activity_date");
      } catch { /* ok */ }
      if (!date) {
        try {
          const q = new URLSearchParams(window.location.search);
          date = q.get("date");
          key = q.get("key");
        } catch { /* ok */ }
        if (!date && !key) { date = params.get("date"); key = params.get("key"); }
      }

      const f = await getFeed();
      if (f === null) { router.replace("/entrar"); return; }
      setFeed(f);
      setLoading(false);

      const hit = key
        ? f.find((it) => it.key === key)
        : date
          ? f.find((it) => it.date_iso === date)
          : null;
      if (hit) open(hit);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, params]);

  async function open(it: FeedItem) {
    setSel(it);
    setTrack(null);
    setAnalysis(null);
    setAnalysisOpen(false);
    setMetaOpen(false);
    setTitleDraft(it.custom_title ? it.name : "");
    setPhotoUrl(null);
    if (it.has_photo) getActivityPhoto(it.key).then(setPhotoUrl).catch(() => {});
    // análise do coach (best-effort, não bloqueia o traçado)
    getActivityAnalysis(it).then(setAnalysis).catch(() => {});
    if (it.has_track) {
      setLoadingTrack(true);
      setTrack(await getTrack(it));
      setLoadingTrack(false);
    }
  }

  // reflete a mudança do item no `sel` E na lista do feed (nome/foto)
  function patchItem(key: string, patch: Partial<FeedItem>) {
    setSel((s) => (s && s.key === key ? { ...s, ...patch } : s));
    setFeed((f) => f?.map((x) => (x.key === key ? { ...x, ...patch } : x)) ?? f);
  }

  async function onSaveTitle() {
    if (!sel) return;
    setSavingMeta(true);
    const t = titleDraft.trim();
    const ok = await setActivityTitle(sel.key, t);
    setSavingMeta(false);
    if (ok) {
      // título vazio volta ao nome original da fonte; sem ele em mãos, usa o rótulo genérico
      patchItem(sel.key, { name: t || (sel.source === "app" ? "Corrida no app" : sel.name), custom_title: !!t });
    }
  }

  // comprime a foto escolhida (≤1280px, JPEG ~0.8) ANTES de subir — disco leve
  function compressToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const max = 1280;
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const cv = document.createElement("canvas");
        cv.width = w; cv.height = h;
        const ctx = cv.getContext("2d");
        if (!ctx) return reject(new Error("canvas"));
        ctx.drawImage(img, 0, 0, w, h);
        resolve(cv.toDataURL("image/jpeg", 0.8));
      };
      img.onerror = () => reject(new Error("img"));
      img.src = URL.createObjectURL(file);
    });
  }

  async function onPickActivityPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !sel) return;
    setSavingMeta(true);
    try {
      const dataUrl = await compressToDataUrl(file);
      const ok = await uploadActivityPhoto(sel.key, dataUrl);
      if (ok) { setPhotoUrl(dataUrl); patchItem(sel.key, { has_photo: true }); }
    } catch { /* ignora */ }
    setSavingMeta(false);
  }

  async function onRemovePhoto() {
    if (!sel) return;
    setSavingMeta(true);
    const ok = await deleteActivityPhoto(sel.key);
    setSavingMeta(false);
    if (ok) { setPhotoUrl(null); patchItem(sel.key, { has_photo: false }); }
  }

  function openEditor() {
    setPhotoImg(null); setStyleIdx(0); setResultUrl(null); setEditor(true);
  }

  function onPickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const img = new Image();
    img.onload = () => setPhotoImg(img);
    img.src = URL.createObjectURL(file);
  }

  // monta o mapa REAL de fundo (tiles + rota) só no estilo "Com mapa" e sem foto
  useEffect(() => {
    if (!editor || CARD_STYLES[styleIdx].transparent || photoImg) { setMapCard(null); return; }
    const pts = track?.points ?? [];
    if (pts.length < 2) { setMapCard(null); return; }
    let alive = true;
    buildMapCard(pts, 1080, 1350).then((c) => { if (alive) setMapCard(c); });
    return () => { alive = false; };
  }, [editor, styleIdx, photoImg, track]);

  // redesenha o preview quando muda estilo/foto/atividade/mapa
  useEffect(() => {
    if (!editor || !sel) return;
    const cv = previewRef.current;
    if (!cv) return;
    refreshCanvasFont();
    const paint = () => {
      cv.width = 1080; cv.height = 1350;
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.textBaseline = "alphabetic";
      ctx.clearRect(0, 0, 1080, 1350);
      const d: CardData = {
        it: sel,
        pts: track?.points ?? [],
        date: fmtDate(sel.datetime ?? sel.date_iso),
        name: sel.name || "Corrida",
        kmTxt: km(sel.distance_km),
        photo: photoImg,
        mapCard,
        splits: track?.splits ?? [],
      };
      CARD_STYLES[styleIdx].draw(ctx, 1080, 1350, d);
    };
    paint();
    // garante a fonte do card (Inter) carregada antes de desenhar — o canvas cai
    // no fallback se pintar antes. Carrega os pesos usados e repinta.
    const fam = CANVAS_FONT.split(",")[0].trim();
    const brand = BRAND_FONT.split(",")[0].trim();
    if (document.fonts && fam) {
      Promise.all([
        document.fonts.load(`800 100px ${fam}`),
        document.fonts.load(`700 40px ${fam}`),
        document.fonts.load(`700 48px ${brand}`),  // wordmark Ritmind (Space Grotesk)
      ]).then(paint).catch(() => {});
      document.fonts.ready.then(paint).catch(() => {});
    }
  }, [editor, styleIdx, photoImg, sel, track, mapCard]);

  // PNG (mantém a transparência) do card atual
  async function makeBlob(): Promise<Blob | null> {
    const cv = previewRef.current;
    if (!cv) return null;
    return new Promise((res) => cv.toBlob((b) => res(b), "image/png"));
  }

  // COPIAR a imagem pro clipboard — pra colar direto no Instagram/story
  async function copyImage() {
    if (!sel) return;
    setSharing(true);
    try {
      const blob = await makeBlob();
      if (!blob) throw new Error("no blob");
      const CI = (window as unknown as { ClipboardItem?: typeof ClipboardItem }).ClipboardItem;
      if (navigator.clipboard && CI) {
        await navigator.clipboard.write([new CI({ "image/png": blob })]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      } else {
        setResultUrl(URL.createObjectURL(blob));
      }
    } catch {
      const blob = await makeBlob();
      if (blob) setResultUrl(URL.createObjectURL(blob));
    }
    setSharing(false);
  }

  async function shareCurrent() {
    if (!sel) return;
    setSharing(true);
    try {
      const blob = await makeBlob();
      if (!blob) throw new Error("no blob");
      const file = new File([blob], "ritmind-corrida.png", { type: "image/png" });
      const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
      if (navShare.canShare && navShare.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], text: `${km(sel.distance_km)} km no Ritmind 🏃` });
          setSharing(false);
          return;
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") { setSharing(false); return; }
        }
      }
      setResultUrl(URL.createObjectURL(blob));
    } catch { /* indisponível */ }
    setSharing(false);
  }

  if (loading || !feed) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // TELA: detalhe
  if (sel) {
    const it = sel;
    return (
      <main className="stage">
        <div className="phone">
          <header className="appbar">
            <button className="icon-btn" aria-label="Voltar" onClick={() => setSel(null)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <div className="title"><div className="k">{fmtDate(it.datetime ?? it.date_iso)}</div><div className="t">{it.name}</div></div>
            <button className="icon-btn" aria-label="Editar" onClick={() => { setMetaOpen((v) => !v); setTitleDraft(it.custom_title ? it.name : ""); }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
            </button>
            <button className="icon-btn" aria-label="Compartilhar" onClick={openEditor}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" /></svg>
            </button>
          </header>

          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickPhoto} />
          <input ref={metaFileRef} type="file" accept="image/*" hidden onChange={onPickActivityPhoto} />

          {metaOpen && (
            <section className="card meta-editor">
              <div className="card-head"><span className="eyebrow">Editar treino</span></div>
              <label className="me-label">Nome</label>
              <div className="me-row">
                <input
                  className="me-input"
                  value={titleDraft}
                  maxLength={80}
                  placeholder="Batize esse treino…"
                  onChange={(e) => setTitleDraft(e.target.value)}
                />
                <button className="btn-mini" disabled={savingMeta} onClick={onSaveTitle}>Salvar</button>
              </div>
              <div className="me-photo">
                <button className="btn-ghost" disabled={savingMeta} onClick={() => metaFileRef.current?.click()}>
                  {it.has_photo ? "Trocar foto" : "📷 Adicionar foto"}
                </button>
                {it.has_photo && <button className="btn-ghost" disabled={savingMeta} onClick={onRemovePhoto}>Remover foto</button>}
              </div>
              <p className="me-hint">A foto aparece pra você e pros amigos que te seguem. {savingMeta ? "Salvando…" : ""}</p>
            </section>
          )}

          {editor && (
            <div className="share-editor">
              <div className="se-inner">
              <header className="appbar">
                <button className="icon-btn" aria-label="Fechar" onClick={() => { setEditor(false); setResultUrl(null); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
                <div className="title"><div className="t">Compartilhar</div></div>
                <span style={{ width: 34 }} />
              </header>

              <div className="se-preview">
                <canvas ref={previewRef} className={`se-canvas${CARD_STYLES[styleIdx].transparent ? " transp" : ""}`} />
              </div>

              <div className="se-styles">
                {CARD_STYLES.map((s, i) => (
                  <button key={s.key} className={`se-chip${i === styleIdx ? " on" : ""}`} onClick={() => setStyleIdx(i)}>{s.label}</button>
                ))}
              </div>

              {CARD_STYLES[styleIdx].transparent ? (
                <p className="se-hint">Fundo transparente — copie e cole por cima da sua foto no story do Instagram 📲</p>
              ) : (
                <div className="se-photo">
                  <button className="btn-ghost" onClick={() => fileRef.current?.click()}>
                    {photoImg ? "Trocar foto" : "📷 Adicionar sua foto"}
                  </button>
                  {photoImg && <button className="btn-ghost" onClick={() => setPhotoImg(null)}>Remover</button>}
                </div>
              )}

              <div className="se-actions">
                <button className="btn se-share" onClick={copyImage} disabled={sharing}>
                  {copied ? "Copiado! ✓" : sharing ? "Gerando…" : "Copiar imagem"}
                </button>
                <button className="btn-ghost" onClick={shareCurrent} disabled={sharing}>Compartilhar</button>
              </div>

              {resultUrl && (
                <div className="se-result" onClick={() => setResultUrl(null)}>
                  <div className="se-result-in" onClick={(e) => e.stopPropagation()}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={resultUrl} alt="Card da corrida" />
                    <p>Segure a imagem para copiar ou salvar — depois cole no seu story 📲</p>
                    <a className="btn" href={resultUrl} download="ritmind-corrida.png">Baixar imagem</a>
                    <button className="btn-ghost" onClick={() => setResultUrl(null)}>Voltar</button>
                  </div>
                </div>
              )}
              </div>
            </div>
          )}

          <ActivityDetailBody
            item={it}
            track={track}
            loadingTrack={loadingTrack}
            photoUrl={photoUrl}
            analysisSlot={analysis?.analysis ? (
              <section className="card coach-analysis">
                <button className="ca-toggle" onClick={() => setAnalysisOpen((o) => !o)} aria-expanded={analysisOpen}>
                  <span className="ca-title">📊 Análise do coach{analysis.workout_type ? ` · ${analysis.workout_type}` : ""}</span>
                  <svg className={`ca-chev${analysisOpen ? " open" : ""}`} viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
                </button>
                {analysisOpen && <p className="ca-text">{analysis.analysis}</p>}
              </section>
            ) : null}
          />

          <CommentsSection activityKey={it.key} />
        </div>
      </main>
    );
  }

  // TELA: feed
  return (
    <main className="stage">
      <div className="phone has-nav">
        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>
        <div className="greet"><h1>Atividades</h1></div>

        <button className="cta-btn" onClick={() => router.push("/correr")}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" /></svg>
          Correr agora (GPS)
        </button>

        {feed.length === 0 ? (
          <div className="card center">
            <p className="muted" style={{ margin: 0 }}>Nenhuma atividade ainda. Grava uma corrida pelo app ou conecta o Strava/Garmin. 🏃</p>
          </div>
        ) : (
          feed.map((it) => (
            <section key={it.key} className="card tap" onClick={() => open(it)}>
              <div className="run-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rr-date">
                    {fmtDate(it.datetime ?? it.date_iso)}{fmtTime(it.datetime) ? ` · ${fmtTime(it.datetime)}` : ""}
                    <span className={`src-tag ${it.source}`}>{it.source === "app" ? "app" : "sync"}</span>
                    {it.has_track && <span className="src-tag track">mapa</span>}
                    {it.has_photo && <span className="src-tag photo">📷</span>}
                    {!!it.comment_count && <span className="src-tag photo">💬 {it.comment_count}</span>}
                  </div>
                  <div className="rr-km">{km(it.distance_km)} km</div>
                  <div className="rr-meta">{it.duration_min} min · {it.pace ?? "—"}/km{it.avg_hr ? ` · ${it.avg_hr} bpm` : ""}</div>
                </div>
                {it.route_preview && <RouteThumb route={it.route_preview} className="rr-thumb" />}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
              </div>
            </section>
          ))
        )}
      </div>
      <BottomNav />
    </main>
  );
}

// useSearchParams (deep-link ?date=/?key=) exige boundary de Suspense no export
// estático do Next — senão a query não chega na 1ª navegação (só no refresh).
export default function AtividadesPage() {
  return (
    <Suspense
      fallback={
        <main className="stage">
          <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
            <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
          </div>
        </main>
      }
    >
      <AtividadesInner />
    </Suspense>
  );
}
