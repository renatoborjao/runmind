"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getHome, saveRun, type RunPayload, type TodaySession, type WorkoutStep } from "@/lib/api";

type Phase = "idle" | "recording" | "paused" | "saving" | "done" | "error";

// sinal do GPS: procurando | bom (conta distância) | fraco (céu fechado) |
// aproximado (Chrome com "localização aproximada": precisão de km) | perdido
type GpsState = "searching" | "good" | "weak" | "approx" | "lost";

// precisão (m) que conta distância; acima disso o ponto é ignorado
const GOOD_ACC = 65;
// acima disto não é céu fechado: é a permissão de localização APROXIMADA
const APPROX_ACC = 300;
// deslocamento mínimo entre pontos (abaixo é tremida do GPS parado)
const MIN_STEP_M = 3;
// velocidade acima disto entre dois pontos = salto de GPS (36 km/h)
const MAX_SPEED_MS = 10;
// sem ponto novo há mais que isto durante a corrida = sinal perdido
const LOST_AFTER_S = 20;

// corrida em andamento guardada localmente — se o app fechar/for pro fundo no
// meio, dá pra recuperar e salvar depois (o GPS da web para com a tela apagada)
const RUN_KEY = "rm_run_progress";

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
  return fmtPaceSec(elapsedS / km);
}

function fmtPaceSec(sec: number | null): string {
  if (sec == null || !isFinite(sec)) return "--:--";
  const t = Math.round(sec); // arredonda o total (nunca "5:60")
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
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

// ---- voz guiada (fala no fone o que está acontecendo) ----
function speak(text: string) {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel(); // não empilha (evita atraso acumulado)
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "pt-BR";
    u.rate = 1.05;
    synth.speak(u);
  } catch { /* ok */ }
}

function spokenAmount(s: Segment): string {
  if (s.dist != null) {
    if (s.dist >= 1000) {
      const km = s.dist / 1000;
      const n = km.toLocaleString("pt-BR");
      return `${n} ${km === 1 ? "quilômetro" : "quilômetros"}`;
    }
    return `${s.dist} metros`;
  }
  if (s.dur != null) {
    return s.dur >= 60 ? `${Math.round(s.dur / 60)} minutos` : `${s.dur} segundos`;
  }
  return "";
}

function spokenPace(s: Segment): string {
  const say = (p: string) => p.replace(":", " e ");
  if (s.paceMin && s.paceMax) return `, ritmo ${say(s.paceMin)} a ${say(s.paceMax)}`;
  if (s.paceMin) return `, ritmo ${say(s.paceMin)}`;
  if (s.kind === "recovery" || s.kind === "easy") return ", leve";
  return "";
}

// o que o atleta precisa saber do sinal — e o que FAZER quando não está bom
function gpsText(state: GpsState, acc: number | null, idle: boolean): string {
  const m = acc != null ? ` (precisão ${acc < 1000 ? `${acc} m` : `${(acc / 1000).toFixed(1).replace(".", ",")} km`})` : "";
  switch (state) {
    case "good":
      return `🟢 GPS pronto${m}${idle ? " — pode iniciar" : ""}`;
    case "weak":
      return `🟡 Sinal fraco${m} — vá pra céu aberto; a distância conta quando firmar`;
    case "approx":
      return `🔴 Localização APROXIMADA${m}. No Chrome: Configurações do site › Localização › ative "Usar localização precisa"`;
    case "lost":
      return idle ? "🟡 Sinal caiu — procurando…" : "🟡 Sinal perdido — procurando… (o tempo segue contando)";
    default:
      return `⏳ Procurando GPS…${idle ? " (em céu aberto leva de segundos a 1 min)" : ""}`;
  }
}

function announce(s: Segment): string {
  const amt = spokenAmount(s);
  // "Tiro 1/4" soa melhor falado como "Tiro 1 de 4"
  const label = s.label.replace("/", " de ");
  return `${label}. ${amt}${spokenPace(s)}.`.replace(/\s+/g, " ").trim();
}

export default function CorrerPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [dist, setDist] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [errMsg, setErrMsg] = useState("");

  // treino do dia (guiado)
  const [session, setSession] = useState<TodaySession | null>(null);
  const [guided, setGuided] = useState(false);
  const [segIdx, setSegIdx] = useState(0);
  const [segDist, setSegDist] = useState(0); // metros no bloco atual
  const [segElapsed, setSegElapsed] = useState(0);
  const [livePace, setLivePace] = useState<number | null>(null);
  const [flash, setFlash] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [recoverable, setRecoverable] = useState<RunPayload | null>(null);
  const [savingRec, setSavingRec] = useState(false);
  // estado REAL do sinal (o GPS liga ao abrir a tela, não só no Iniciar)
  const [gps, setGps] = useState<GpsState>("searching");
  const [gpsAcc, setGpsAcc] = useState<number | null>(null);
  const [saveFailed, setSaveFailed] = useState(false); // envio falhou (ficou pendente)

  const voiceRef = useRef(true);
  const lastNudge = useRef(0);
  const lastPersist = useRef(0);
  const lastFixAt = useRef(0); // Date.now() do último ponto recebido
  useEffect(() => { voiceRef.current = voiceOn; }, [voiceOn]);

  const segments = useRef<Segment[]>([]);
  const segIdxRef = useRef(0);
  const segStartDist = useRef(0);
  const segStartElapsed = useRef(0);
  const recent = useRef<{ t: number; d: number }[]>([]);

  const watchId = useRef<number | null>(null);
  const wakeLock = useRef<{ release: () => void } | null>(null);
  // âncora da distância: o último ponto ACEITO (com o instante, pra velocidade)
  const last = useRef<{ lat: number; lon: number; ms: number } | null>(null);
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
    // corrida não salva de uma sessão anterior (app fechou/foi pro fundo no meio)?
    try {
      const raw = localStorage.getItem(RUN_KEY);
      if (raw) {
        const r = JSON.parse(raw);
        if (r && r.distance_m > 50 && r.duration_s > 30) setRecoverable(r);
        else localStorage.removeItem(RUN_KEY);
      }
    } catch { /* ok */ }
    // liga o GPS JÁ na tela de início: o 1º sinal do celular leva de segundos
    // a um minuto — quando ele tocar em Iniciar, o sinal já está firme
    startWatch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // mantém a tela ligada de novo quando o app volta ao foco durante a corrida
  // (o wake lock se solta sozinho quando a aba fica oculta)
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible" && phaseRef.current === "recording") requestWake();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
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

      // sinal sumiu no meio da corrida (túnel, prédio): avisa, não derruba
      if (lastFixAt.current && Date.now() - lastFixAt.current > LOST_AFTER_S * 1000) {
        setGps("lost");
      }

      // guarda o progresso local a cada ~5s (rede de segurança se o app fechar)
      if (e - lastPersist.current >= 5) { persistProgress(e); lastPersist.current = e; }

      // pace ao vivo (janela ~25s)
      let lp: number | null = null;
      const buf = recent.current;
      if (buf.length >= 2) {
        const cutoff = e - 25;
        const old = buf.find((s) => s.t >= cutoff) ?? buf[0];
        const dd = distRef.current - old.d;
        const dt = e - old.t;
        lp = dd > 20 && dt > 3 ? (dt / 60) / (dd / 1000) : null;
        setLivePace(lp);
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
        const nextSeg = segments.current[idx + 1];
        segIdxRef.current = idx + 1;
        segStartDist.current = distRef.current;
        segStartElapsed.current = e;
        setSegIdx(idx + 1);
        setSegDist(0); setSegElapsed(0);
        cue();
        if (voiceRef.current) speak(announce(nextSeg));
        lastNudge.current = e;
        setFlash(true);
        setTimeout(() => setFlash(false), 900);
        return;
      }

      // nudge de pace por voz: só em bloco com alvo, no máximo a cada ~40s, e
      // não nos primeiros 15s do bloco (deixa acelerar/desacelerar antes)
      if (voiceRef.current && coveredT > 15 && e - lastNudge.current > 40) {
        const lo = paceToSec(seg.paceMin), hi = paceToSec(seg.paceMax ?? seg.paceMin);
        if (lp != null && lo != null && hi != null) {
          if (lp > hi + 12) { speak("Acelera um pouco."); lastNudge.current = e; }
          else if (lp < lo - 12) { speak("Segura o ritmo, tá rápido."); lastNudge.current = e; }
        }
      }
    }, 500);
    return () => clearInterval(id);
  }, [guided]);

  useEffect(() => {
    return () => { stopWatch(); releaseWake(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onPos(pos: GeolocationPosition) {
    const acc = pos.coords.accuracy;
    const now = Date.now();
    lastFixAt.current = now;
    setGpsAcc(acc != null ? Math.round(acc) : null);
    // GPS de navegador reporta 20–60 m fácil (1º fix, área urbana): até 65 m
    // conta. Centenas de metros/km não é céu fechado — é o Chrome com
    // localização APROXIMADA (o atleta precisa ligar a precisa).
    const state: GpsState = acc == null || acc <= GOOD_ACC ? "good" : acc > APPROX_ACC ? "approx" : "weak";
    setGps(state);
    if (phaseRef.current !== "recording" || state !== "good") return;

    const p = { lat: pos.coords.latitude, lon: pos.coords.longitude, ms: now };
    if (!last.current) {
      last.current = p;
      points.current.push({ lat: p.lat, lon: p.lon, t: Math.floor((now - startTs.current) / 1000) });
      return;
    }
    const d = haversine(last.current, p);
    // tremida parado: não move a âncora (passos pequenos se ACUMULAM até
    // passar do mínimo — antes a âncora andava e a distância sumia)
    if (d < MIN_STEP_M) return;
    // salto de GPS: velocidade impossível desde o último ponto aceito. Pela
    // VELOCIDADE, não por um teto fixo de metros — sinal espaçado (20 s sem
    // ponto) é corrida de verdade, não salto
    const dt = (now - last.current.ms) / 1000;
    if (dt > 0 && d / dt > MAX_SPEED_MS) return;
    distRef.current += d;
    setDist(distRef.current);
    recent.current.push({ t: nowElapsedSec(), d: distRef.current });
    if (recent.current.length > 120) recent.current.shift();
    last.current = p;
    points.current.push({ lat: p.lat, lon: p.lon, t: Math.floor((now - startTs.current) / 1000) });
  }

  // só PERMISSÃO NEGADA encerra. Demora/indisponível (1º sinal, prédio,
  // túnel) é passageiro: o GPS segue procurando e a corrida continua — antes
  // qualquer demora de 15 s derrubava a corrida ("Não consegui pegar o GPS")
  function onErr(e: GeolocationPositionError) {
    if (e.code === 1) {
      stopWatch();
      setErrMsg("Permissão de localização negada. Libere a localização (precisa) pro site nas configurações do Chrome e tente de novo.");
      if (phaseRef.current === "idle") setPhase("error");
      else setGps("lost");
      return;
    }
    setGps(lastFixAt.current ? "lost" : "searching");
  }

  function startWatch() {
    if (watchId.current != null) return;
    if (!("geolocation" in navigator)) {
      setErrMsg("Este aparelho não tem GPS disponível no navegador."); setPhase("error"); return;
    }
    // sem `timeout`: o GPS procura o tempo que precisar (o aviso de sinal
    // perdido é nosso, no tick)
    watchId.current = navigator.geolocation.watchPosition(onPos, onErr, {
      enableHighAccuracy: true, maximumAge: 0,
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

  function persistProgress(durS: number) {
    try {
      const payload: RunPayload = {
        started_at: new Date(startTs.current).toISOString(),
        duration_s: durS,
        distance_m: Math.round(distRef.current),
        avg_pace: paceStr(distRef.current, durS),
        points: points.current,
      };
      localStorage.setItem(RUN_KEY, JSON.stringify(payload));
    } catch { /* ok */ }
  }
  function clearProgress() {
    try { localStorage.removeItem(RUN_KEY); } catch { /* ok */ }
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
    startTs.current = Date.now();
    segStart.current = Date.now();
    elapsedBase.current = 0;
    distRef.current = 0; setDist(0); setElapsed(0);
    // a distância conta a partir do 1º ponto BOM depois do Iniciar
    last.current = null; points.current = []; recent.current = [];
    lastNudge.current = 0; lastPersist.current = 0;
    setRecoverable(null); clearProgress();
    setPhase("recording"); phaseRef.current = "recording";
    startWatch();
    requestWake();
    // fala o 1º bloco AQUI (dentro do gesto do toque) — destrava a voz no iOS
    if (useGuide && session && segments.current.length && voiceRef.current) {
      speak(`Bora! ${announce(segments.current[0])}`);
    }
  }

  function onPause() {
    elapsedBase.current += Date.now() - segStart.current;
    setPhase("paused"); phaseRef.current = "paused";
  }
  function onResume() {
    // o que ele andou PAUSADO não conta: a âncora recomeça no próximo ponto
    last.current = null;
    segStart.current = Date.now();
    setPhase("recording"); phaseRef.current = "recording";
  }

  async function onFinish() {
    if (phaseRef.current === "recording") { elapsedBase.current += Date.now() - segStart.current; }
    stopWatch(); releaseWake();
    const durS = Math.floor(elapsedBase.current / 1000);
    setPhase("saving"); phaseRef.current = "saving";

    const payload: RunPayload = {
      started_at: new Date(startTs.current).toISOString(),
      duration_s: durS,
      distance_m: Math.round(distRef.current),
      avg_pace: paceStr(distRef.current, durS),
      points: points.current,
    };

    // BLINDADO: o envio NUNCA pode travar a tela em "Salvando…". Se falhar
    // (rede/erro), não perde a corrida — mantém no localStorage pra recuperar
    // depois — e chega a "done" do mesmo jeito, avisando que ficou pendente.
    let ok = false;
    try {
      ok = await saveRun(payload);
    } catch {
      ok = false;
    }

    if (ok) {
      clearProgress();
      setSaveFailed(false);
    } else {
      try { localStorage.setItem(RUN_KEY, JSON.stringify(payload)); } catch { /* ok */ }
      setSaveFailed(true);
    }

    setElapsed(durS);
    if (guided && voiceRef.current) speak("Treino concluído! Mandou bem.");
    setPhase("done"); phaseRef.current = "done";
  }

  // recupera uma corrida interrompida (salva localmente) e manda pro servidor
  async function saveRecovered() {
    if (!recoverable) return;
    setSavingRec(true);
    try {
      await saveRun(recoverable);
      clearProgress();
      setRecoverable(null);
      router.push("/atividades");
    } finally {
      setSavingRec(false);
    }
  }
  function discardRecovered() {
    clearProgress();
    setRecoverable(null);
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
            <button className="btn" style={{ marginTop: 16 }} onClick={() => { setPhase("idle"); setGps("searching"); startWatch(); }}>Tentar de novo</button>
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

            {guided && (recording || paused) && (
              <button
                className="voice-toggle"
                onClick={() => {
                  const on = !voiceOn;
                  setVoiceOn(on);
                  if (!on) { try { window.speechSynthesis?.cancel(); } catch { /* ok */ } }
                  else if (seg) speak(announce(seg));
                }}
              >
                {voiceOn ? "🔊 Voz ligada" : "🔇 Voz desligada"}
              </button>
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

            {phase === "idle" && recoverable && (
              <div className="card" style={{ marginTop: 8 }}>
                <p className="notice" style={{ margin: 0 }}>
                  Achei uma corrida que não foi salva:{" "}
                  <strong>{(recoverable.distance_m / 1000).toFixed(2).replace(".", ",")} km</strong>{" "}
                  em <strong>{fmtTime(recoverable.duration_s)}</strong>. Quer salvar?
                </p>
                <div className="run-actions" style={{ marginTop: 12 }}>
                  <button className="run-btn go" disabled={savingRec} onClick={saveRecovered}>
                    {savingRec ? "Salvando…" : "Salvar"}
                  </button>
                  <button className="run-btn hold" disabled={savingRec} onClick={discardRecovered}>Descartar</button>
                </div>
              </div>
            )}

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
                <div className="badge" style={{ margin: "0 auto 10px" }}><span className="dot" />{saveFailed ? "Corrida guardada" : "Corrida salva"}</div>
                <p style={{ margin: 0, fontSize: 15 }}>Boa! {km} km em {fmtTime(elapsed)} · {paceStr(dist, elapsed)}/km 🏃</p>
                {saveFailed && (
                  <p className="notice" style={{ marginTop: 10, fontSize: 12.5 }}>
                    Não consegui enviar agora (conexão). Guardei a corrida aqui no aparelho — quando você abrir a tela de correr de novo com internet, é só tocar em Salvar. 💾
                  </p>
                )}
                <button className="btn" style={{ marginTop: 16 }} onClick={() => router.push("/atividades")}>Ver minhas atividades</button>
                <button className="btn-ghost" style={{ marginTop: 10 }} onClick={() => router.push("/inicio")}>Voltar pro início</button>
              </div>
            )}

            {(phase === "idle" || recording || paused) && (
              <p className={`gps-status ${gps}`}>{gpsText(gps, gpsAcc, phase === "idle")}</p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
