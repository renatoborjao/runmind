"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  followAthlete, getAthlete, getAthleteActivities, toggleKudos, unfollowAthlete,
  type AthleteProfile, type SocialActivity,
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

export default function AtletaPage() {
  const router = useRouter();
  const [id, setId] = useState<string | null>(null);
  const [prof, setProf] = useState<AthleteProfile | null>(null);
  const [acts, setActs] = useState<SocialActivity[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("id");
    setId(q);
  }, []);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      const p = await getAthlete(id);
      setProf(p);
      if (p?.can_view) setActs(await getAthleteActivities(id));
      else setActs(null);
      setLoading(false);
    })();
  }, [id]);

  async function onFollow() {
    if (!prof) return;
    setBusy(true);
    if (prof.relationship === "following" || prof.relationship === "requested") {
      await unfollowAthlete(prof.id);
      setProf({ ...prof, relationship: "none", can_view: prof.privacy === "public" });
      setActs(prof.privacy === "public" ? await getAthleteActivities(prof.id) : null);
    } else {
      const rel = await followAthlete(prof.id);
      const canView = rel === "following";
      setProf({ ...prof, relationship: rel, can_view: canView || prof.can_view });
      if (canView) setActs(await getAthleteActivities(prof.id));
    }
    setBusy(false);
  }

  async function onKudos(a: SocialActivity) {
    const liked = await toggleKudos(a.owner, a.key);
    setActs((prev) => prev?.map((x) => x.key === a.key ? { ...x, kudos_by_me: liked, kudos: x.kudos + (liked ? 1 : -1) } : x) ?? prev);
  }

  // abre o detalhe da atividade do amigo (mapa/splits, sem análise). Passa o
  // item pelo sessionStorage (canal confiável no export estático do Next).
  function openActivity(a: SocialActivity) {
    try { sessionStorage.setItem("rm_friend_activity", JSON.stringify(a)); } catch { /* ok */ }
    router.push(`/atleta/atividade?owner=${a.owner}&key=${encodeURIComponent(a.key)}`);
  }

  const followLabel = !prof ? "" : prof.relationship === "following" ? "Seguindo" : prof.relationship === "requested" ? "Solicitado" : prof.privacy === "private" ? "Solicitar" : "Seguir";

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/comunidade")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Perfil</div></div>
          <span style={{ width: 34 }} />
        </header>

        {loading ? (
          <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>
        ) : !prof ? (
          <div className="card center"><p className="muted" style={{ margin: 0 }}>Atleta não encontrado.</p></div>
        ) : (
          <>
            <section className="card prof-head">
              <Avatar name={prof.name} src={prof.avatar} size={72} />
              <h2>{prof.name}</h2>
              {prof.follows_me && <span className="ath-tag">segue você</span>}
              {prof.bio && <p className="prof-bio">{prof.bio}</p>}
              <div className="prof-counts">
                <div><b>{prof.counts.followers}</b><span>seguidores</span></div>
                <div><b>{prof.counts.following}</b><span>seguindo</span></div>
                {prof.journey && <div><b>{prof.journey.km_total}</b><span>km no app</span></div>}
              </div>
              {prof.relationship !== "self" && (
                <button className={`btn${prof.relationship === "none" ? "" : " btn-ghost"}`} onClick={onFollow} disabled={busy}>
                  {followLabel}
                </button>
              )}
            </section>

            {prof.journey && (
              <div className="qstats">
                <div className="qstat"><div className="v">{prof.journey.km_total}<small> km</small></div><div className="k">Total</div></div>
                <div className="qstat"><div className="v">{prof.journey.runs}</div><div className="k">Corridas</div></div>
                <div className="qstat"><div className="v">{String(prof.journey.biggest_km).replace(".", ",")}<small> km</small></div><div className="k">Maior</div></div>
              </div>
            )}

            {!prof.can_view ? (
              <div className="card center">
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>🔒 Perfil com solicitação. {prof.relationship === "requested" ? "Pedido enviado — aguarde a aprovação pra ver as atividades." : "Solicite pra ver as atividades."}</p>
              </div>
            ) : acts && acts.length > 0 ? (
              <>
                <div className="card-head" style={{ margin: "4px 2px 0" }}><span className="eyebrow">Atividades</span></div>
                {acts.map((a) => (
                  <section className="card social-act tap" key={a.key} onClick={() => openActivity(a)}>
                    <div className="sa-when">
                      {fmtWhen(a.datetime ?? a.date_iso)}
                      {a.has_track && <span className="src-tag track">mapa</span>}
                      {a.has_photo && <span className="src-tag photo">📷</span>}
                    </div>
                    <div className="sa-title">{a.name}</div>
                    <div className="sa-row">
                      <div className="sa-stats">
                        <div><b>{a.distance_km.toFixed(2).replace(".", ",")}</b><span>km</span></div>
                        <div><b>{a.pace ?? "—"}</b><span>/km</span></div>
                        <div><b>{a.duration_min}</b><span>min</span></div>
                        {a.avg_hr != null && <div><b>{a.avg_hr}</b><span>bpm</span></div>}
                      </div>
                      {a.route_preview && <RouteThumb route={a.route_preview} className="sa-thumb" />}
                    </div>
                    <div className="sa-foot">
                      <button className={`kudos${a.kudos_by_me ? " on" : ""}`} onClick={(e) => { e.stopPropagation(); onKudos(a); }}>
                        <svg viewBox="0 0 24 24" width="17" height="17" fill={a.kudos_by_me ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-6 0v4H5l1.5 10.5A2 2 0 0 0 8.5 21h7a2 2 0 0 0 2-1.5L19 9z" /></svg>
                        {a.kudos > 0 ? a.kudos : ""}
                      </button>
                      <span className="sa-open">Ver treino ›</span>
                    </div>
                  </section>
                ))}
              </>
            ) : (
              <div className="card center"><p className="muted" style={{ margin: 0, fontSize: 13 }}>Sem atividades ainda.</p></div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
