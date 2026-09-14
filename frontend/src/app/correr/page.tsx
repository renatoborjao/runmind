"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { saveRun } from "@/lib/api";

type Phase = "idle" | "recording" | "paused" | "saving" | "done" | "error";

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

export default function CorrerPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [dist, setDist] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [gpsOk, setGpsOk] = useState<boolean | null>(null);
  const [errMsg, setErrMsg] = useState("");

  const watchId = useRef<number | null>(null);
  const wakeLock = useRef<{ release: () => void } | null>(null);
  const last = useRef<{ lat: number; lon: number } | null>(null);
  const points = useRef<{ lat: number; lon: number; t: number }[]>([]);
  const distRef = useRef(0);
  const startTs = useRef(0);
  const elapsedBase = useRef(0); // ms acumulados antes do segmento atual
  const segStart = useRef(0);
  const phaseRef = useRef<Phase>("idle");

  useEffect(() => { phaseRef.current = phase; }, [phase]);

  // tick do cronômetro
  useEffect(() => {
    const id = setInterval(() => {
      if (phaseRef.current === "recording") {
        const ms = elapsedBase.current + (Date.now() - segStart.current);
        setElapsed(Math.floor(ms / 1000));
      }
    }, 500);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    return () => { stopWatch(); releaseWake(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onPos(pos: GeolocationPosition) {
    if (phaseRef.current !== "recording") return;
    const acc = pos.coords.accuracy;
    const p = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    if (acc != null && acc > 30) return; // ponto ruim, ignora
    if (last.current) {
      const d = haversine(last.current, p);
      // ignora jitter (<2m) e saltos absurdos (>25m/tick ~ erro de GPS)
      if (d >= 2 && d < 60) {
        distRef.current += d;
        setDist(distRef.current);
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

  async function onStart() {
    setGpsOk(true);
    startTs.current = Date.now();
    segStart.current = Date.now();
    elapsedBase.current = 0;
    distRef.current = 0; setDist(0); setElapsed(0);
    last.current = null; points.current = [];
    setPhase("recording");
    phaseRef.current = "recording";
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
                <button className="run-btn go" onClick={onStart}>Iniciar</button>
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
