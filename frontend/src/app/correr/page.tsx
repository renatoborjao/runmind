"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getHome, saveRun, type TodaySession, type WorkoutStep } from "@/lib/api";

type Phase = "idle" | "recording" | "paused" | "saving" | "done" | "error";

// ---- treino guiado: achatar os blocos numa sequência linear ----
interface Segment {
  label: string;
  kind: string;
  dist: number | null; // metros-alvo
  dur: number | null;  // segundos-alvo
  paceMin: string | null;
  paceMax: string | null;
}

const KIND_PT: Record<string, string> = {
  warmup: "Aquecimento", interval: "Tiro", recovery: "Recuperação",
  cooldown: "Desaquecimento", run: "Rodagem", tempo: "Ritmo", easy: "Leve",
};

function segLabel(kind: string, rep?: number, reps?: number): string {
  const base = KIND_PT[kind] ?? "Bloco";
  return rep && reps ? `${base} ${rep}/${reps}` : base;
}

function flatten(steps: WorkoutStep[] | undefined): Segment[] {
  const out: Segment[] = [];
  const walk = (s: WorkoutStep, rep?: number, reps?: number) => {
    if (s.steps && s.steps.length && s.reps && s.reps > 1) {
      for (let r = 1; r <= s.reps; r++) s.steps.forEach((c) => walk(c, r, s.reps ?? undefined));
      return;
    }
    if (s.steps && s.steps.length) { s.steps.forEach((c) => walk(c, rep, reps)); return; }
    out.push({
      label: segLabel(s.kind, rep, reps),
      kind: s.kind,
      dist: s.distance_m ?? null,
      dur: s.duration_sec ?? null,
      paceMin: s.pace_min ?? null,
      paceMax: s.pace_max ?? null,
    });
  };
  (steps ?? []).forEach((s) => walk(s));
  return out;
}

function paceToSec(p: string | null): number | null {
  if (!p) return null;
  const m = p.match(/(\d+):(\d+)/);
  if (!m) return null;
  return parseInt(m[1]) * 60 + parseInt(m[2]);
}

function targetLabel(s: Segment): string {
  const amt = s.dist != null
    ? (s.dist >= 1000 ? `${(s.dist / 1000).toString().replace(".", ",")} km` : `${s.dist} m`)
    : s.dur != null ? (s.dur >= 60 ? `${Math.round(s.dur / 60)} min` : `${s.dur}s`) : "livre";
  const pace = s.paceMin && s.paceMax ? `${s.paceMin}–${s.paceMax}` : s.paceMin ? s.paceMin : "leve";
  return `${amt} · ${pace}/km`;
}

function haversine(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function fmtTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function paceStr(distM: number, elapsedS: number): string {
  const km = distM / 1000;
  if (km < 0.05 || elapsedS < 5) return "--:--";
  const p = elapsedS / 60 / km;
  return `${Math.floor(p)}:${String(Math.round((p % 1) * 60)).padStart(2, "0")}`;
}

function fmtPaceSec(sec: number | null): string {
  if (sec == null || !isFinite(sec)) return "--:--";
  return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;
}

function cue() {
  try { (navigator as Navigator & { vibrate?: (p: number[]) => void }).vibrate?.([180, 90, 180]); } catch { /* ok */ }
  try {
    const AC = (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext });
    const Ctx = AC.AudioContext || AC.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    o.start(); o.stop(ctx.currentTime + 0.36);
  } catch { /* ok */ }
}

export default function CorrerPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [dist, setDist] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [gpsOk, setGpsOk] = useState<boolean | null>(null);
  const [errMsg, setErrMsg] = useState("");

  // treino do dia (guiado)
  const [session, setSession] = useState<TodaySession | null>(null);
  const [guided, setGuided] = useState(false);
  const [segIdx, setSegIdx] = useState(0);
  const [segDist, setSegDist] = useState(0); // metros no bloco atual
  const [segElapsed, setSegElapsed] = useState(0);
  const [livePace, setLivePace] = useState<number | null>(null);
  const [flash, setFlash] = useState(false);

  const segments = useRef<Segment[]>([]);
  const segIdxRef = useRef(0);
  const segStartDist = useRef(0);
  const segStartElapsed = useRef(0);
  const recent = useRef<{ t: number; d: number }[]>([]);

  const watchId = useRef<number | null>(null);
  const wakeLock = useRef<{ release: () => void } | null>(null);
  const last = useRef<{ lat: number; lon: number } | null>(null);
  const points = useRef<{ lat: number; lon: number; t: number }[]>([]);
  const distRef = useRef(0);
  const startTs = useRef(0);
  const elapsedBase = useRef(0);
  const segStart = useRef(0);
  const phaseRef = useRef<Phase>("idle");

  useEffect(() => { phaseRef.current = phase; }, [phase]);

  useEffect(() => {
    (async () => {
      const h = await getHome();
      if (h?.today?.session && (h.today.session.steps?.length ?? 0) > 0) setSession(h.today.session);
    })();
  }, []);

  function nowElapsedSec(): number {
    const ms = elapsedBase.current + (Date.now() - segStart.current);
    return Math.floor(ms / 1000);
  }

  // tick: cronômetro + progresso do bloco + pace ao vivo + avanço de bloco
  useEffect(() => {
    const id = setInterval(() => {
      if (phaseRef.current !== "recording") return;
      const e = nowElapsedSec();
      setElapsed(e);

      // pace ao vivo (janela ~25s)
      const buf = recent.current;
      if (buf.length >= 2) {
        const cutoff = e - 25;
        const old = buf.find((s) => s.t >= cutoff) ?? buf[0];
        const dd = distRef.current - old.d;
        const dt = e - old.t;
        setLivePace(dd > 20 && dt > 3 ? (dt / 60) / (dd / 1000) : null);
      }

      if (!guided || segments.current.length === 0) return;

      const idx = segIdxRef.current;
      const seg = segments.current[idx];
      if (!seg) return;
      const coveredD = distRef.current - segStartDist.current;
      const coveredT = e - segStartElapsed.current;
      setSegDist(coveredD);
      setSegElapsed(coveredT);

      const doneByDist = seg.dist != null && coveredD >= seg.dist;
      const doneByTime = seg.dur != null && coveredT >= seg.dur;
      if ((doneByDist || doneByTime) && idx < segments.current.length - 1) {
        segIdxRef.current = idx + 1;
        segStartDist.current = distRef.current;
        segStartElapsed.current = e;
        setSegIdx(idx + 1);
        setSegDist(0); setSegElapsed(0);
        cue();
        setFlash(true);
        setTimeout(() => setFlash(false), 900);
      }
    }, 500);
    return () => clearInterval(id);
  }, [guided]);

  useEffect(() => {
    return () => { stopWatch(); releaseWake(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onPos(pos: GeolocationPosition) {
    if (phaseRef.current !== "recording") return;
    const acc = pos.coords.accuracy;
    const p = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    if (acc != null && acc > 30) return;
    if (last.current) {
      const d = haversine(last.current, p);
      if (d >= 2 && d < 60) {
        distRef.current += d;
        setDist(distRef.current);
        recent.current.push({ t: nowElapsedSec(), d: distRef.current });
        if (recent.current.length > 120) recent.current.shift();
      }
    }
    last.current = p;
    points.current.push({ ...p, t: Math.floor((Date.now() - startTs.current) / 1000) });
  }

  function onErr(e: GeolocationPositionError) {
    setGpsOk(false);
    setErrMsg(e.code === 1 ? "Permissão de localização negada. Libere o GPS pro app nas configurações do navegador." : "Não consegui pegar o GPS. Tenta num lugar aberto.");
    setPhase("error");
  }

  function startWatch() {
    if (!("geolocation" in navigator)) {
      setGpsOk(false); setErrMsg("Este aparelho não tem GPS disponível no navegador."); setPhase("error"); return;
    }
    watchId.current = navigator.geolocation.watchPosition(onPos, onErr, {
      enableHighAccuracy: true, maximumAge: 1000, timeout: 15000,
    });
  }

  function stopWatch() {
    if (watchId.current != null) { navigator.geolocation.clearWatch(watchId.current); watchId.current = null; }
  }

  async function requestWake() {
    try {
      const wl = (navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => void }> } }).wakeLock;
      if (wl) wakeLock.current = await wl.request("screen");
    } catch { /* ok */ }
  }
  function releaseWake() {
    try { wakeLock.current?.release(); wakeLock.current = null; } catch { /* ok */ }
  }

  function begin(useGuide: boolean) {
    if (useGuide && session) {
      segments.current = flatten(session.steps);
      setGuided(segments.current.length > 0);
    } else {
      setGuided(false);
    }
    segIdxRef.current = 0; setSegIdx(0);
    segStartDist.current = 0; segStartElapsed.current = 0;
    setSegDist(0); setSegElapsed(0); setLivePace(null);
    setGpsOk(true);
    startTs.current = Date.now();
    segStart.current = Date.now();
    elapsedBase.current = 0;
    distRef.current = 0; setDist(0); setElapsed(0);
    last.current = null; points.current = []; recent.current = [];
    setPhase("recording"); phaseRef.current = "recording";
    startWatch();
    requestWake();
  }

  function onPause() {
    elapsedBase.current += Date.now() - segStart.current;
    setPhase("paused"); phaseRef.current = "paused";
  }
  function onResume() {
    segStart.current = Date.now();
    setPhase("recording"); phaseRef.current = "recording";
  }

  async function onFinish() {
    if (phaseRef.current === "recording") { elapsedBase.current += Date.now() - segStart.current; }
    stopWatch(); releaseWake();
    const durS = Math.floor(elapsedBase.current / 1000);
    setPhase("saving"); phaseRef.current = "saving";
    await saveRun({
      started_at: new Date(startTs.current).toISOString(),
      duration_s: durS,
      distance_m: Math.round(distRef.current),
      avg_pace: paceStr(distRef.current, durS),
      points: points.current,
    });
    setElapsed(durS);
    setPhase("done"); phaseRef.current = "done";
  }

  const km = (dist / 1000).toFixed(2).replace(".", ",");
  const recording = phase === "recording";
  const paused = phase === "paused";

  // estado do bloco atual (guiado)
  const seg = guided ? segments.current[segIdx] : null;
  const next = guided ? segments.current[segIdx + 1] : null;
  const segTarget = seg?.dist ?? null;
  const segTargetT = seg?.dur ?? null;
  const prog = segTarget != null ? Math.min(1, segDist / segTarget) : segTargetT != null ? Math.min(1, segElapsed / segTargetT) : 0;
  const remain = segTarget != null
    ? `faltam ${Math.max(0, Math.round(segTarget - segDist))} m`
    : segTargetT != null ? `faltam ${fmtTime(Math.max(0, segTargetT - segElapsed))}` : "";

  // cor do pace ao vivo vs alvo
  let paceTone = "";
  const pMin = paceToSec(seg?.paceMin ?? null);
  const pMax = paceToSec(seg?.paceMax ?? null);
  if (livePace != null && (pMin != null || pMax != null)) {
    const lo = pMin ?? pMax!, hi = pMax ?? pMin!;
    if (livePace >= lo - 8 && livePace <= hi + 8) paceTone = "good";
    else if (livePace >= lo - 20 && livePace <= hi + 20) paceTone = "warn";
    else paceTone = "bad";
  }

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => { stopWatch(); releaseWake(); router.push("/inicio"); }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Correr</div></div>
          <span style={{ width: 34 }} />
        </header>

        {phase === "error" ? (
          <div className="card center">
            <p className="notice err">{errMsg}</p>
            <button className="btn" style={{ marginTop: 16 }} onClick={() => { setPhase("idle"); setGpsOk(null); }}>Tentar de novo</button>
          </div>
        ) : (
          <>
            {/* GUIA do bloco atual */}
            {guided && seg && (recording || paused) && (
              <div className={`guide-card ${seg.kind}${flash ? " flash" : ""}`}>
                <div className="guide-top">
                  <span className="guide-step">Bloco {segIdx + 1}/{segments.current.length}</span>
                  {seg.paceMin && <span className={`guide-pace ${paceTone}`}>{fmtPaceSec(livePace)}<small>/km</small></span>}
                </div>
                <div className="guide-label">{seg.label}</div>
                <div className="guide-target">{targetLabel(seg)}</div>
                <div className="guide-prog"><i style={{ width: `${Math.round(prog * 100)}%` }} /></div>
                <div className="guide-remain">{remain}</div>
                {next && <div className="guide-next">Depois: {next.label} · {targetLabel(next)}</div>}
                {!next && <div className="guide-next">Último bloco — finaliza quando terminar. 🏁</div>}
              </div>
            )}

            <div className="run-metrics">
              <div className="run-main">
                <div className="run-km">{km}</div>
                <div className="run-unit">quilômetros</div>
              </div>
              <div className="run-sub">
                <div><div className="run-v">{fmtTime(elapsed)}</div><div className="run-l">tempo</div></div>
                <div><div className="run-v">{paceStr(dist, elapsed)}</div><div className="run-l">pace /km</div></div>
              </div>
            </div>

            {phase === "idle" && (
              <>
                <p className="muted center" style={{ margin: "8px 24px" }}>
                  Mantém o app aberto e a tela ligada durante a corrida. 📍
                </p>
                {session && (session.workout_type || (session.steps?.length ?? 0) > 0) ? (
                  <>
                    <button className="run-btn go" onClick={() => begin(true)}>
                      Treino do dia: {session.workout_type || "guiado"}
                    </button>
                    <button className="btn-ghost" style={{ marginTop: 10 }} onClick={() => begin(false)}>Corrida livre</button>
                  </>
                ) : (
                  <button className="run-btn go" onClick={() => begin(false)}>Iniciar</button>
                )}
              </>
            )}

            {(recording || paused) && (
              <div className="run-actions">
                {recording ? (
                  <button className="run-btn hold" onClick={onPause}>Pausar</button>
                ) : (
                  <button className="run-btn go" onClick={onResume}>Retomar</button>
                )}
                <button className="run-btn stop" onClick={onFinish}>Finalizar</button>
              </div>
            )}

            {phase === "saving" && <p className="auth-sub center" style={{ marginTop: 12 }}>Salvando…</p>}

            {phase === "done" && (
              <div className="card center" style={{ marginTop: 8 }}>
                <div className="badge" style={{ margin: "0 auto 10px" }}><span className="dot" />Corrida salva</div>
                <p style={{ margin: 0, fontSize: 15 }}>Boa! {km} km em {fmtTime(elapsed)} · {paceStr(dist, elapsed)}/km 🏃</p>
                <button className="btn" style={{ marginTop: 16 }} onClick={() => router.push("/atividades")}>Ver minhas atividades</button>
                <button className="btn-ghost" style={{ marginTop: 10 }} onClick={() => router.push("/inicio")}>Voltar pro início</button>
              </div>
            )}

            {gpsOk === true && phase !== "done" && (
              <p className="muted center" style={{ fontSize: 11, marginTop: 8 }}>GPS ativo 🟢</p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
