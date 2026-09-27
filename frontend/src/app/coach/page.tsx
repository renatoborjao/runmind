"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  apiMediaSrc,
  getCoachMessages,
  sendCoachMessage,
  sendCoachPhoto,
  sendCoachVoice,
  type ChatMsg,
} from "@/lib/api";

const TELEGRAM_COACH = "https://t.me/runmind_coach_bot";

// mesmo teto do servidor (voice_max_seconds): passou disso, para sozinho
const MAX_RECORD_SECONDS = 300;

const FAIL_REPLY = "Ops, não consegui responder agora. Tenta de novo daqui a pouco. 🙏";

type Msg = ChatMsg & { lid?: string };

type Attachment = { data: string; preview: string | null; name: string };

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

// rótulo do botão do cartão pelo destino
function actionLabel(url?: string | null): string {
  if (!url) return "Ver";
  if (url.startsWith("/treino")) return "Ver treino";
  if (url.startsWith("/atividades")) return "Ver atividade";
  if (url.startsWith("/evolucao")) return "Ver evolução";
  if (url.startsWith("/provas")) return "Ver provas";
  if (url.startsWith("/tenis")) return "Ver tênis";
  if (url.startsWith("/corpo")) return "Ver meu corpo";
  return "Abrir";
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

// Foto do celular vem enorme: reduz pra JPEG (lado maior 1600) antes de subir.
// Se o navegador não decodifica (ex.: HEIC fora do Safari), manda o original.
async function imageToJpeg(file: File, max = 1600, quality = 0.85): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = url;
    });
    const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", quality);
  } catch {
    return blobToDataUrl(file);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function mmss(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function CoachPage() {
  const router = useRouter();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState<string | null>(null); // rótulo do "digitando"
  const [loading, setLoading] = useState(true);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recStart, setRecStart] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [zoom, setZoom] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    (async () => {
      const m = await getCoachMessages();
      if (m === null) { router.replace("/entrar"); return; }
      setMsgs(m);
      setLoading(false);
    })();
  }, [router]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, sending, attachment]);

  // cronômetro da gravação (+ para sozinho no teto)
  useEffect(() => {
    if (recStart === null) return;
    const t = setInterval(() => {
      const n = Date.now();
      setNow(n);
      if ((n - recStart) / 1000 >= MAX_RECORD_SECONDS) stopRecording(true);
    }, 250);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recStart]);

  // saiu da tela gravando: solta o microfone
  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  function pushReply(reply: string | null) {
    setMsgs((m) => [...m, { role: "assistant", text: reply ?? FAIL_REPLY, at: null }]);
  }

  async function onSend() {
    if (sending) return;
    const text = input.trim();

    if (attachment) {
      const att = attachment;
      setAttachment(null);
      setInput("");
      setMsgs((m) => [...m, {
        role: "user",
        text: att.preview ? text : `📄 ${att.name}${text ? `\n${text}` : ""}`,
        at: null,
        local_image: att.preview,
      }]);
      setSending("Coach olhando…");
      const reply = await sendCoachPhoto(att.data, text);
      setSending(null);
      pushReply(reply);
      return;
    }

    if (!text) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text, at: null }]);
    setSending("Coach digitando…");
    const reply = await sendCoachMessage(text);
    setSending(null);
    pushReply(reply);
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNotice(null);
    if (file.type === "application/pdf") {
      if (file.size > 10 * 1024 * 1024) { setNotice("Esse PDF é grande demais (máx. 10 MB)."); return; }
      setAttachment({ data: await blobToDataUrl(file), preview: null, name: file.name });
      return;
    }
    if (!file.type.startsWith("image/") && !/\.(heic|heif)$/i.test(file.name)) {
      setNotice("Manda uma foto ou um PDF. 🙂");
      return;
    }
    const data = await imageToJpeg(file);
    setAttachment({ data, preview: data.startsWith("data:image/jpeg") ? data : null, name: file.name });
  }

  async function startRecording() {
    setNotice(null);
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setNotice("Seu navegador não grava áudio aqui. 😕 Escreve pra mim?");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setNotice("Preciso do microfone pra gravar — libera nas permissões do navegador.");
      return;
    }
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"]
      .find((t) => MediaRecorder.isTypeSupported?.(t));
    const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunksRef.current = [];
    rec.ondataavailable = (ev) => { if (ev.data.size) chunksRef.current.push(ev.data); };
    rec.start();
    recRef.current = rec;
    streamRef.current = stream;
    const t = Date.now();
    setNow(t);
    setRecStart(t);
  }

  function stopRecording(send: boolean) {
    const rec = recRef.current;
    if (!rec || recStart === null) return;
    const duration = (Date.now() - recStart) / 1000;
    recRef.current = null;
    setRecStart(null);
    rec.onstop = () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (!send || duration < 0.8) return; // toque sem querer: descarta
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
      sendVoice(blob, duration);
    };
    rec.stop();
  }

  async function sendVoice(blob: Blob, duration: number) {
    const lid = `v${Date.now()}`;
    setMsgs((m) => [...m, { role: "user", text: `🎤 Áudio (${mmss(duration)}) · transcrevendo…`, at: null, lid }]);
    setSending("Coach ouvindo…");
    const res = await sendCoachVoice(await blobToDataUrl(blob), duration);
    setSending(null);
    setMsgs((m) => m.map((x) => (x.lid === lid
      ? { ...x, text: res?.transcript ? `🎤 ${res.transcript}` : `🎤 Áudio (${mmss(duration)})` }
      : x)));
    pushReply(res?.reply ?? null);
  }

  const recording = recStart !== null;
  const canSend = !!attachment || !!input.trim();

  return (
    <main className="stage">
      <div className="phone has-nav has-composer">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Coach</span></div>
          <a className="link" href={TELEGRAM_COACH} target="_blank" rel="noopener noreferrer">no Telegram ↗</a>
        </div>

        {loading ? (
          <p className="auth-sub center" style={{ margin: "30px 0" }}>Carregando…</p>
        ) : msgs.length === 0 ? (
          <p className="chat-empty">Fala com teu coach 👋<br />Escreve, manda um áudio 🎤 ou uma foto 📷 — do treino, do relógio, da planilha, de onde doeu.</p>
        ) : (
          <div className="chat-msgs">
            {msgs.map((m, i) => {
              if (m.role === "coach") {
                const hasAction = !!m.url && m.url !== "/inicio/";
                return (
                  <div key={i} className="coach-card">
                    {m.title && <div className="cc-title">{m.title}</div>}
                    <div className="cc-text">{m.text}</div>
                    {hasAction && (
                      <button className="cc-action" onClick={() => router.push(m.url!)}>
                        {actionLabel(m.url)}
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
                      </button>
                    )}
                  </div>
                );
              }
              const img = m.local_image ?? (m.image_url ? apiMediaSrc(m.image_url) : null);
              return (
                <div key={i} className={`msg ${m.role === "user" ? "user" : "bot"}${img ? " has-img" : ""}`}>
                  {img && <img className="msg-img" src={img} alt="Foto enviada" onClick={() => setZoom(img)} />}
                  {m.text && <span>{m.text}</span>}
                </div>
              );
            })}
            {sending && <div className="msg bot typing">{sending}</div>}
            <div ref={endRef} />
          </div>
        )}

      </div>

      <div className="composer">
        {notice && (
          <div className="composer-row composer-notice" onClick={() => setNotice(null)}>{notice}</div>
        )}

        {attachment && (
          <div className="composer-row attach-preview">
            {attachment.preview
              ? <img src={attachment.preview} alt="Prévia" />
              : <span className="attach-doc">📄</span>}
            <span className="attach-name">{attachment.preview ? "Foto pronta — escreve algo se quiser" : attachment.name}</span>
            <button className="attach-x" aria-label="Remover anexo" onClick={() => setAttachment(null)}>✕</button>
          </div>
        )}

        {recording ? (
          <>
            <button className="icon-round ghost" aria-label="Cancelar gravação" onClick={() => stopRecording(false)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
            </button>
            <div className="rec-bar"><span className="rec-dot" />Gravando {mmss((now - recStart!) / 1000)}</div>
            <button className="send-btn" aria-label="Enviar áudio" onClick={() => stopRecording(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="#04231d" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h15M13 6l6 6-6 6" /></svg>
            </button>
          </>
        ) : (
          <>
            <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onPickFile} />
            <button className="icon-round ghost" aria-label="Mandar foto" onClick={() => fileRef.current?.click()} disabled={!!sending}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
            </button>
            <textarea
              rows={1}
              placeholder={attachment ? "Legenda (opcional)…" : "Fala com teu coach…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
            />
            {canSend ? (
              <button className="send-btn" onClick={onSend} disabled={!!sending} aria-label="Enviar">
                <svg viewBox="0 0 24 24" fill="none" stroke="#04231d" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h15M13 6l6 6-6 6" /></svg>
              </button>
            ) : (
              <button className="send-btn" onClick={startRecording} disabled={!!sending} aria-label="Gravar áudio">
                <svg viewBox="0 0 24 24" fill="none" stroke="#04231d" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
              </button>
            )}
          </>
        )}
      </div>

      {zoom && (
        <div className="img-zoom" onClick={() => setZoom(null)}>
          <img src={zoom} alt="Foto ampliada" />
        </div>
      )}

      <BottomNav />
    </main>
  );
}
