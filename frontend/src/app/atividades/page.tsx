"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  deleteActivityPhoto,
  getActivityAnalysis,
  getActivityPhoto,
  getFeed,
  getShareContext,
  getTrack,
  setActivityTitle,
  uploadActivityPhoto,
  type CoachAnalysis,
  type FeedItem,
  type RunSplit,
  type ShareContext,
  type TrackData,
} from "@/lib/api";
import { drawCoachDiz, drawPeito, drawPlanoFeito, planHasTargets, type RunExtras } from "@/lib/run-card-extras";
import { ActivityDetailBody, CommentsSection, fmtDate, fmtTime, km, RouteThumb } from "../activity-detail";
import {
  CANVAS_FONT, bottomScrim, canvasBlob, copyBlob, drawBg, drawBrand,
  drawStatsSpread, fmtDur, outlinedText, paintWhenFontsReady, roundRect,
  shareBlob, topScrim, withShadow,
} from "@/lib/share-canvas";

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
const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function shortDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]} ${y}`;
}

interface CardData { it: FeedItem; pts: { lat: number; lon: number }[]; date: string; name: string; kmTxt: string; photo: HTMLImageElement | null; mapCard: HTMLCanvasElement | null; splits: RunSplit[]; extras: RunExtras; }

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
  withShadow(ctx, () => outlinedText(ctx, d.date, W - 64, 100, 4));
  ctx.textAlign = "left";
}
function footer(ctx: CanvasRenderingContext2D, W: number, H: number) {
  ctx.fillStyle = "#9A9BAE"; ctx.font = `600 22px ${CANVAS_FONT}`; ctx.textAlign = "center";
  withShadow(ctx, () => outlinedText(ctx, "ritmind", W / 2, H - 34, 3));
  ctx.textAlign = "left";
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
      outlinedText(ctx, lab, cx, baseY, Math.max(3, labSize * 0.11));
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 ${valSize}px ${CANVAS_FONT}`;
      outlinedText(ctx, val, cx, baseY + valSize + 10, Math.max(3, valSize * 0.11));
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
      ctx.fillStyle = "#FFFFFF"; ctx.font = `700 46px ${CANVAS_FONT}`; outlinedText(ctx, lab, cx, y, 5);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 96px ${CANVAS_FONT}`; outlinedText(ctx, val, cx, y + 100, 9);
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

// PARCIAIS — barra por km (mais rápido = barra maior), estilo Strava (template 5).
// Nada de painel de fundo (destoava, "não parece flutuar" — feedback do
// Renato): contraste vem de contorno no texto + barra com trilho escuro
// (halo), igual ao traçado da rota. Também mais estreito/baixo que a v1 —
// não precisa ocupar o card inteiro pra ser legível.
function styleParciais(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawParciais(ctx, W, H, d, false);
}

// COMPLETO — parciais + linha de dados (distância/ritmo/tempo) + UMA marca só.
// Antes o atleta colava 2 stickers (Parciais + Cantinho) e o "Ritmind" saía
// duplicado no story (pedido do Renato).
function styleCompleto(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawParciais(ctx, W, H, d, true);
}

function drawParciais(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData, withStats: boolean) {
  const splits = d.splits.filter((s) => s.sec > 0);
  const titleY = 200;
  // com a linha de dados o bloco alarga um pouco (3 números grandes precisam caber)
  const labelX = 90, barX = 172, valueX = Math.round(W * (withStats ? 0.72 : 0.62));
  const blockCenterX = (labelX + valueX) / 2; // marca centraliza no BLOCO, não no card
  const statsCells = shareCells(d.it).slice(0, 3);

  withShadow(ctx, () => {
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 44px ${CANVAS_FONT}`; ctx.textAlign = "left";
    outlinedText(ctx, "Parciais por KM", labelX, titleY, 7);
  });

  if (!splits.length) {
    withShadow(ctx, () => {
      ctx.fillStyle = "#E7E8F0"; ctx.font = `600 30px ${CANVAS_FONT}`;
      outlinedText(ctx, "Sem parciais nesta corrida", labelX, 250, 5);
    });
    const afterY = withStats ? drawStatsSpread(ctx, labelX, valueX, 330, statsCells) + 30 : 280;
    withShadow(ctx, () => drawBrand(ctx, blockCenterX, afterY + 50, 40, true));
    return;
  }

  // fonte de LABEL/PACE em tamanho FIXO e legível — não escala com a
  // quantidade de splits (isso é o que ficou minúsculo/ilegível na v2).
  // rowH acompanha esse tamanho; só encolhe de verdade em corrida MUITO
  // longa (meia/maratona), e aí a fonte encolhe junto (proporcional).
  const rowHFull = 46;
  // a linha de dados come ~150px da altura — a lista ganha menos orçamento
  const rowH = withStats
    ? Math.max(20, Math.min(rowHFull, 720 / splits.length))
    : Math.max(30, Math.min(rowHFull, 900 / splits.length));
  const scale = rowH / rowHFull;
  const labelFont = Math.round(34 * scale);
  const paceFont = Math.round(30 * scale);
  const barH = Math.max(14, Math.round(24 * scale));
  const barMaxW = valueX - 130 - barX;

  const top = 244;
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

    ctx.fillStyle = "#FFFFFF"; ctx.font = `700 ${labelFont}px ${CANVAS_FONT}`; ctx.textAlign = "left";
    outlinedText(ctx, label, labelX, y + labelFont * 0.34, 4);

    ctx.font = `700 ${paceFont}px ${CANVAS_FONT}`; ctx.textAlign = "right";
    outlinedText(ctx, s.pace ?? "—", valueX, y + paceFont * 0.32, 4);
    ctx.textAlign = "left";
  });

  if (withStats) {
    // dados logo abaixo das barras, na mesma largura; marca única no pé
    const statsEnd = drawStatsSpread(ctx, labelX, valueX, listBottom + 64, statsCells);
    withShadow(ctx, () => drawBrand(ctx, blockCenterX, Math.min(statsEnd + 70, H - 40), 40, true));
    return;
  }

  // marca colada logo abaixo da última linha, centralizada no BLOCO
  withShadow(ctx, () => drawBrand(ctx, blockCenterX, brandY, 40, true));
}

// `needs`: estilo que depende de dado do backend (sessão do plano / frase do
// coach) só aparece quando esse dado existe pra corrida
interface CardStyle { key: string; label: string; transparent: boolean; needs?: "planned" | "quote"; draw: (c: CanvasRenderingContext2D, W: number, H: number, d: CardData) => void; }
const CARD_STYLES: CardStyle[] = [
  { key: "centralizado", label: "Central", transparent: true, draw: styleCentralizado },
  { key: "rota", label: "Rota", transparent: true, draw: styleRota },
  { key: "cantinho", label: "Cantinho", transparent: true, draw: styleCantinho },
  { key: "parciais", label: "Parciais", transparent: true, draw: styleParciais },
  { key: "completo", label: "Parciais + dados", transparent: true, draw: styleCompleto },
  { key: "plano", label: "Plano × feito", transparent: true, needs: "planned", draw: (c, W, H, d) => drawPlanoFeito(c, W, H, d.it, d.extras) },
  { key: "coach", label: "Coach diz", transparent: true, needs: "quote", draw: (c, W, H, d) => drawCoachDiz(c, W, H, d.it, d.extras) },
  { key: "peito", label: "Número de peito", transparent: true, draw: (c, W, H, d) => drawPeito(c, W, H, d.it, d.extras) },
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
  // estilo escolhido pela CHAVE (a lista muda quando os extras do backend
  // chegam — índice apontaria pra outro estilo)
  const [styleKey, setStyleKey] = useState(CARD_STYLES[0].key);
  const [shareCtx, setShareCtx] = useState<ShareContext | null>(null);
  const styles = useMemo(
    () => CARD_STYLES.filter((st) => !st.needs || (st.needs === "planned" ? planHasTargets(shareCtx?.planned) : shareCtx?.quote)),
    [shareCtx],
  );
  const styleIdx = Math.max(0, styles.findIndex((st) => st.key === styleKey));
  const style = styles[styleIdx];
  const setStyleIdx = (i: number) => setStyleKey(styles[Math.max(0, Math.min(styles.length - 1, i))].key);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mapCard, setMapCard] = useState<HTMLCanvasElement | null>(null);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const chipRefs = useRef<(HTMLButtonElement | null)[]>([]);
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
    setPhotoImg(null); setStyleKey(CARD_STYLES[0].key); setResultUrl(null); setEditor(true);
    // extras do backend (plano da sessão + frase do coach): os estilos que
    // dependem deles aparecem quando chegam
    setShareCtx(null);
    if (sel) getShareContext(sel).then(setShareCtx);
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
    if (!editor || style.transparent || photoImg) { setMapCard(null); return; }
    const pts = track?.points ?? [];
    if (pts.length < 2) { setMapCard(null); return; }
    let alive = true;
    buildMapCard(pts, 1080, 1350).then((c) => { if (alive) setMapCard(c); });
    return () => { alive = false; };
  }, [editor, style, photoImg, track]);

  // troca de estilo pelo chip mantém o chip ativo visível na fileira (que
  // agora rola escondida, sem barra) — importante quando o swipe no card
  // muda pra um estilo fora da tela.
  useEffect(() => {
    if (!editor) return;
    chipRefs.current[styleIdx]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [editor, styleIdx]);

  // deslizar o CARD (não só tocar no chip) também troca de estilo — gesto
  // natural tipo carrossel. Pointer events cobrem toque e mouse igual.
  function onPreviewPointerDown(e: React.PointerEvent) {
    swipeStart.current = { x: e.clientX, y: e.clientY };
  }
  function onPreviewPointerUp(e: React.PointerEvent) {
    const start = swipeStart.current;
    swipeStart.current = null;
    if (!start) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
    setStyleIdx(dx < 0 ? styleIdx + 1 : styleIdx - 1);
  }

  // redesenha o preview quando muda estilo/foto/atividade/mapa
  useEffect(() => {
    if (!editor || !sel) return;
    const cv = previewRef.current;
    if (!cv) return;
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
        extras: {
          date: shortDate(sel.date_iso),
          planned: shareCtx?.planned ?? null,
          quote: shareCtx?.quote ?? null,
        },
      };
      style.draw(ctx, 1080, 1350, d);
    };
    paintWhenFontsReady(paint);
  }, [editor, style, photoImg, sel, track, mapCard, shareCtx]);

  // PNG (mantém a transparência) do card atual
  const makeBlob = () => canvasBlob(previewRef.current);

  // COPIAR a imagem pro clipboard — pra colar direto no Instagram/story
  async function copyImage() {
    if (!sel) return;
    setSharing(true);
    const blob = await makeBlob();
    if (blob) {
      if (await copyBlob(blob)) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      } else {
        setResultUrl(URL.createObjectURL(blob));
      }
    }
    setSharing(false);
  }

  async function shareCurrent() {
    if (!sel) return;
    setSharing(true);
    const blob = await makeBlob();
    if (blob) {
      const r = await shareBlob(blob, "ritmind-corrida.png", `${km(sel.distance_km)} km no Ritmind 🏃`);
      if (r === "unsupported") setResultUrl(URL.createObjectURL(blob));
    }
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

              <div className="se-preview" onPointerDown={onPreviewPointerDown} onPointerUp={onPreviewPointerUp}>
                <canvas ref={previewRef} className={`se-canvas${style.transparent ? " transp" : ""}`} />
              </div>

              <div className="se-styles">
                {styles.map((s, i) => (
                  <button
                    key={s.key}
                    ref={(el) => { chipRefs.current[i] = el; }}
                    className={`se-chip${i === styleIdx ? " on" : ""}`}
                    onClick={() => setStyleIdx(i)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>

              {style.transparent ? (
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
            shareSlot={
              <button className="btn-ghost share-cta" onClick={openEditor}>
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" /></svg>
                Compartilhar
              </button>
            }
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
