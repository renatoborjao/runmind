"use client";

// Resumo semanal/mensal na Evolução + editor de COMPARTILHAR do resumo (mesmo
// fluxo do card de corrida: preview ao vivo, estilos, copiar/compartilhar PNG).

import { useEffect, useMemo, useRef, useState } from "react";
import { getFeed, getPeriodGoal, type FeedItem } from "@/lib/api";
import { fmtKm, fmtPace, periodSummary, type PeriodKind, type PeriodSummary } from "@/lib/period-summary";
import { CARD_W, canvasBlob, copyBlob, fmtDur, paintWhenFontsReady, shareBlob } from "@/lib/share-canvas";
import { SUMMARY_LAYOUTS, drawSummaryCard, summaryCanvasHeight, type SummaryBackground } from "@/lib/summary-card";

// semana: km por dia; mês: km por semana (rótulo "7–13")
function Bars({ s }: { s: PeriodSummary }) {
  const W = 340, padT = 20;
  const padB = s.kind === "month" ? 32 : 20;
  const H = 104 + padB;
  const n = s.bars.length;
  const gap = s.kind === "week" ? 10 : 16;
  const bw = (W - gap * (n - 1)) / n;
  const max = Math.max(1, ...s.bars.map((d) => d.km));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={s.kind === "week" ? "Km por dia" : "Km por semana"}>
      {s.bars.map((d, i) => {
        const h = d.km > 0 ? Math.max(4, ((H - padB - padT) * d.km) / max) : 2;
        const x = i * (bw + gap);
        const y = H - padB - h;
        return (
          <g key={i}>
            {d.km > 0 && (
              <text x={x + bw / 2} y={y - 5} textAnchor="middle" fontSize="12" fontWeight="700" fontFamily="var(--font-display)" fill="var(--ink)">{fmtKm(d.km)}</text>
            )}
            <rect x={x} y={y} width={bw} height={h} rx={3}
              fill={d.km > 0 ? "var(--accent)" : "var(--line)"} opacity={d.future ? 0.5 : 1} />
            <text x={x + bw / 2} y={d.sub ? H - 17 : H - 4} textAnchor="middle" fontSize="11.5" fontWeight="700" fontFamily="var(--font-display)" fill="var(--ink-soft)">{d.label}</text>
            {d.sub && (
              <text x={x + bw / 2} y={H - 3} textAnchor="middle" fontSize="10.5" fontWeight="600" fontFamily="var(--font-display)" fill="var(--muted)">{d.sub}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default function ResumoSection() {
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [kind, setKind] = useState<PeriodKind>("week");
  const [offset, setOffset] = useState(0);
  const [editor, setEditor] = useState(false);

  useEffect(() => { getFeed().then((f) => setFeed(f ?? [])).catch(() => setFeed([])); }, []);

  const base = useMemo(() => (feed ? periodSummary(feed, kind, offset) : null), [feed, kind, offset]);

  // meta de km do período pelo PLANO (card "Meta" + linha no app); cache por
  // período pra não rebuscar ao ir e voltar nas setas
  const [goals, setGoals] = useState<Record<string, number | null>>({});
  const goalKey = base ? `${base.startIso}_${base.endIso}` : "";
  useEffect(() => {
    if (!base || goalKey in goals) return;
    getPeriodGoal(base.startIso, base.endIso).then((g) => setGoals((m) => ({ ...m, [goalKey]: g })));
  }, [base, goalKey, goals]);
  const s = useMemo(() => (base ? { ...base, goalKm: goals[goalKey] ?? null } : null), [base, goals, goalKey]);

  if (!s) return null;

  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Resumo</span></div>
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={kind === "week" ? "on" : ""} onClick={() => { setKind("week"); setOffset(0); }}>Semana</button>
        <button className={kind === "month" ? "on" : ""} onClick={() => { setKind("month"); setOffset(0); }}>Mês</button>
      </div>

      <div className="rs-nav">
        <button className="icon-btn" aria-label="Período anterior" onClick={() => setOffset((o) => o - 1)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </button>
        <span className="rs-label">{s.label}{s.isCurrent ? " · atual" : ""}</span>
        <button className="icon-btn" aria-label="Próximo período" disabled={offset >= 0} onClick={() => setOffset((o) => Math.min(0, o + 1))}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
        </button>
      </div>

      <div className="rs-km">
        <span className="big">{fmtKm(s.km)}</span><small> km</small>
        {s.deltaPct != null && (
          <span className={`rs-delta${s.deltaPct >= 0 ? " up" : ""}`}>
            {s.deltaPct >= 0 ? "▲" : "▼"} {Math.abs(s.deltaPct)}% {s.vsLabel}
          </span>
        )}
      </div>

      <Bars s={s} />

      {s.goalKm != null && (
        <p className="rs-goal">
          Meta do plano: <b>{fmtKm(s.km)} de {fmtKm(s.goalKm, 0)} km</b> · {Math.round((s.km / s.goalKm) * 100)}%
        </p>
      )}

      <div className="prog-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", marginTop: 10 }}>
        <div className="stat"><div className="k">Treinos</div><div className="big">{s.runs}</div></div>
        <div className="stat"><div className="k">Tempo</div><div className="big" style={{ fontSize: 20 }}>{s.seconds > 0 ? fmtDur(s.seconds) : "—"}</div></div>
        <div className="stat"><div className="k">Ritmo</div><div className="big" style={{ fontSize: 20 }}>{fmtPace(s.paceSec)}</div></div>
      </div>

      <button className="btn-ghost share-cta" disabled={s.runs === 0} onClick={() => setEditor(true)}>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" /></svg>
        {s.runs === 0 ? "Sem corridas nesse período" : "Compartilhar resumo"}
      </button>

      {editor && <ResumoEditor s={s} onClose={() => setEditor(false)} />}
    </section>
  );
}

function ResumoEditor({ s, onClose }: { s: PeriodSummary; onClose: () => void }) {
  const [layoutIdx, setLayoutIdx] = useState(0);
  const [background, setBackground] = useState<SummaryBackground>("transparent");
  const [photo, setPhoto] = useState<HTMLImageElement | null>(null);
  const [sharing, setSharing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // "Meta" só aparece quando o período tem plano
  const layouts = SUMMARY_LAYOUTS.filter((l) => l.key !== "meta" || s.goalKm != null);
  const layout = layouts[Math.min(layoutIdx, layouts.length - 1)];
  const transparent = background === "transparent";
  const cardH = summaryCanvasHeight(layout.key);
  const filename = s.kind === "week" ? "ritmind-semana.png" : "ritmind-mes.png";

  useEffect(() => {
    const cv = previewRef.current;
    if (!cv) return;
    paintWhenFontsReady(() => {
      cv.width = CARD_W; cv.height = cardH;
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.textBaseline = "alphabetic";
      ctx.clearRect(0, 0, CARD_W, cardH);
      drawSummaryCard(ctx, CARD_W, cardH, s, layout.key, background, transparent ? null : photo);
    });
  }, [s, layout, background, transparent, photo, cardH]);

  function onPickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const img = new Image();
    img.onload = () => setPhoto(img);
    img.src = URL.createObjectURL(file);
  }

  async function copyImage() {
    setSharing(true);
    const blob = await canvasBlob(previewRef.current);
    if (blob) {
      if (await copyBlob(blob)) { setCopied(true); setTimeout(() => setCopied(false), 2500); }
      else setResultUrl(URL.createObjectURL(blob));
    }
    setSharing(false);
  }

  async function shareCurrent() {
    setSharing(true);
    const blob = await canvasBlob(previewRef.current);
    if (blob) {
      const r = await shareBlob(blob, filename, `${fmtKm(s.km)} km ${s.kind === "week" ? "na semana" : "no mês"} com o Ritmind 🏃`);
      if (r === "unsupported") setResultUrl(URL.createObjectURL(blob));
    }
    setSharing(false);
  }

  return (
    <div className="share-editor">
      <div className="se-inner">
        <header className="appbar">
          <button className="icon-btn" aria-label="Fechar" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
          <div className="title"><div className="t">{s.title}</div></div>
          <span style={{ width: 34 }} />
        </header>

        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickPhoto} />

        <div className="se-preview">
          <canvas ref={previewRef} className={`se-canvas${transparent ? " transp" : ""}${cardH < CARD_W ? " wide" : ""}`} />
        </div>

        <div className="se-styles">
          {layouts.map((l, i) => (
            <button key={l.key} className={`se-chip${i === layoutIdx ? " on" : ""}`} onClick={() => setLayoutIdx(i)}>
              {l.label}
            </button>
          ))}
        </div>

        <div className="seg" style={{ marginBottom: 6 }}>
          <button className={transparent ? "on" : ""} onClick={() => setBackground("transparent")}>Transparente</button>
          <button className={!transparent ? "on" : ""} onClick={() => setBackground("card")}>Card</button>
        </div>

        {transparent ? (
          <p className="se-hint">Fundo transparente — copie e cole por cima da sua foto no story do Instagram 📲</p>
        ) : (
          <div className="se-photo">
            <button className="btn-ghost" onClick={() => fileRef.current?.click()}>
              {photo ? "Trocar foto" : "📷 Adicionar sua foto"}
            </button>
            {photo && <button className="btn-ghost" onClick={() => setPhoto(null)}>Remover</button>}
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
              <img src={resultUrl} alt="Card do resumo" />
              <p>Segure a imagem para copiar ou salvar — depois cole no seu story 📲</p>
              <a className="btn" href={resultUrl} download={filename}>Baixar imagem</a>
              <button className="btn-ghost" onClick={() => setResultUrl(null)}>Voltar</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
