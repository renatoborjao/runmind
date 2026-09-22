"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  acceptFollow, followAthlete, getAthletes, getFollowRequests, getSocialFeed,
  rejectFollow, toggleKudos, unfollowAthlete,
  type AthleteCard, type Relationship, type SocialActivity,
} from "@/lib/api";
import { RouteThumb } from "../activity-detail";

function Avatar({ name, src, size = 40 }: { name: string; src?: string | null; size?: number }) {
  const initials = (name || "?").trim().split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="av" src={src} alt={name} style={{ width: size, height: size }} />;
  }
  return <span className="av av-txt" style={{ width: size, height: size, fontSize: size * 0.36 }}>{initials || "🏃"}</span>;
}

function fmtWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }) + " · " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function relLabel(r: Relationship): string {
  return r === "following" ? "Seguindo" : r === "requested" ? "Solicitado" : "Seguir";
}

function KudosBtn({ a, onToggle }: { a: SocialActivity; onToggle: () => void }) {
  return (
    <button className={`kudos${a.kudos_by_me ? " on" : ""}`} onClick={onToggle}>
      <svg viewBox="0 0 24 24" width="17" height="17" fill={a.kudos_by_me ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-6 0v4H5l1.5 10.5A2 2 0 0 0 8.5 21h7a2 2 0 0 0 2-1.5L19 9z" /></svg>
      {a.kudos > 0 ? a.kudos : ""}
    </button>
  );
}

export default function ComunidadePage() {
  const router = useRouter();
  const [tab, setTab] = useState<"feed" | "descobrir">("feed");
  const [feed, setFeed] = useState<SocialActivity[] | null>(null);
  const [athletes, setAthletes] = useState<AthleteCard[]>([]);
  const [requests, setRequests] = useState<AthleteCard[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [f, a, r] = await Promise.all([getSocialFeed(), getAthletes(), getFollowRequests()]);
      setFeed(f); setAthletes(a); setRequests(r); setLoading(false);
    })();
  }, []);

  async function onKudos(a: SocialActivity) {
    const liked = await toggleKudos(a.owner, a.key);
    setFeed((prev) => prev?.map((x) => x.key === a.key && x.owner === a.owner
      ? { ...x, kudos_by_me: liked, kudos: x.kudos + (liked ? 1 : -1) } : x) ?? prev);
  }

  // abre o detalhe da atividade do amigo (mapa/splits, sem análise). Passa o
  // item pelo sessionStorage (canal confiável no export estático do Next).
  function openActivity(a: SocialActivity) {
    try { sessionStorage.setItem("rm_friend_activity", JSON.stringify(a)); } catch { /* ok */ }
    router.push(`/atleta/atividade?owner=${a.owner}&key=${encodeURIComponent(a.key)}`);
  }

  async function onFollow(c: AthleteCard) {
    if (c.relationship === "following" || c.relationship === "requested") {
      await unfollowAthlete(c.id);
      setAthletes((p) => p.map((x) => x.id === c.id ? { ...x, relationship: "none" } : x));
    } else {
      const rel = await followAthlete(c.id);
      setAthletes((p) => p.map((x) => x.id === c.id ? { ...x, relationship: rel } : x));
    }
  }

  async function onAccept(id: string) {
    await acceptFollow(id);
    setRequests((p) => p.filter((x) => x.id !== id));
  }
  async function onReject(id: string) {
    await rejectFollow(id);
    setRequests((p) => p.filter((x) => x.id !== id));
  }

  return (
    <main className="stage">
      <div className="phone has-nav">
        <div className="greet"><h1>Social</h1></div>

        <div className="seg">
          <button className={tab === "feed" ? "on" : ""} onClick={() => setTab("feed")}>Feed</button>
          <button className={tab === "descobrir" ? "on" : ""} onClick={() => setTab("descobrir")}>
            Descobrir{requests.length > 0 ? ` (${requests.length})` : ""}
          </button>
        </div>

        {loading ? (
          <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>
        ) : tab === "feed" ? (
          feed && feed.length > 0 ? (
            feed.map((a) => (
              <section className="card social-act" key={`${a.owner}-${a.key}`}>
                <div className="sa-head" onClick={() => router.push(`/atleta?id=${a.owner}`)}>
                  <Avatar name={a.owner_name || a.owner} src={a.owner_avatar} />
                  <div><div className="sa-name">{a.owner_name || a.owner}</div><div className="sa-when">{fmtWhen(a.datetime ?? a.date_iso)}</div></div>
                </div>
                <div className="sa-body tap" onClick={() => openActivity(a)}>
                  <div className="sa-title">{a.name}{a.has_track && <span className="src-tag track">mapa</span>}{a.has_photo && <span className="src-tag photo">📷</span>}</div>
                  <div className="sa-row">
                    <div className="sa-stats">
                      <div><b>{a.distance_km.toFixed(2).replace(".", ",")}</b><span>km</span></div>
                      <div><b>{a.pace ?? "—"}</b><span>/km</span></div>
                      <div><b>{a.duration_min}</b><span>min</span></div>
                      {a.avg_hr != null && <div><b>{a.avg_hr}</b><span>bpm</span></div>}
                    </div>
                    {a.route_preview && <RouteThumb route={a.route_preview} className="sa-thumb" />}
                  </div>
                </div>
                <div className="sa-foot"><KudosBtn a={a} onToggle={() => onKudos(a)} />{!!a.comment_count && <span className="sa-count" onClick={() => openActivity(a)}>💬 {a.comment_count}</span>}<span className="sa-open" onClick={() => openActivity(a)}>Ver treino ›</span></div>
              </section>
            ))
          ) : (
            <div className="card center"><p className="muted" style={{ margin: 0 }}>Siga atletas pra ver as corridas deles aqui. Vai em <b>Descobrir</b>. 👟</p></div>
          )
        ) : (
          <>
            {requests.length > 0 && (
              <section className="card">
                <div className="card-head"><span className="eyebrow">Pedidos pra te seguir</span></div>
                {requests.map((c) => (
                  <div className="ath-row" key={c.id}>
                    <div className="ath-id" onClick={() => router.push(`/atleta?id=${c.id}`)}>
                      <Avatar name={c.name} src={c.avatar} size={38} />
                      <div className="ath-name">{c.name}</div>
                    </div>
                    <div className="req-btns">
                      <button className="btn-mini" onClick={() => onAccept(c.id)}>Aceitar</button>
                      <button className="btn-mini ghost" onClick={() => onReject(c.id)}>✕</button>
                    </div>
                  </div>
                ))}
              </section>
            )}

            <section className="card">
              <div className="card-head"><span className="eyebrow">Atletas</span></div>
              {athletes.length === 0 ? (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>Nenhum outro atleta ainda.</p>
              ) : athletes.map((c) => (
                <div className="ath-row" key={c.id}>
                  <div className="ath-id" onClick={() => router.push(`/atleta?id=${c.id}`)}>
                    <Avatar name={c.name} src={c.avatar} size={38} />
                    <div>
                      <div className="ath-name">{c.name}</div>
                      {c.privacy === "private" && <div className="ath-tag">perfil com solicitação</div>}
                    </div>
                  </div>
                  <button className={`btn-mini${c.relationship === "none" ? "" : " ghost"}`} onClick={() => onFollow(c)}>
                    {relLabel(c.relationship)}
                  </button>
                </div>
              ))}
            </section>
          </>
        )}
      </div>
      <BottomNav />
    </main>
  );
}
