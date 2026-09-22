"use client";

// Detalhe da atividade de UM amigo — mesma cara da minha (mapa, stats, zonas,
// gráficos, parciais), via o componente compartilhado. SEM a análise do coach
// (privada de cada atleta) e sem o compartilhar (é a corrida do outro). Só
// leitura + kudos.

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getActivityPhoto, getAthleteActivities, getTrack, toggleKudos,
  type SocialActivity, type TrackData,
} from "@/lib/api";
import { ActivityDetailBody, fmtDate } from "../../activity-detail";

function AtividadeAmigoInner() {
  const router = useRouter();
  const [owner, setOwner] = useState<string | null>(null);
  const [item, setItem] = useState<SocialActivity | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      // A atividade chega pelo sessionStorage (gravada no perfil ANTES de navegar
      // — canal confiável no export estático do Next, onde a query nem sempre
      // chega na 1ª navegação client-side). A URL (?owner=&key=) é fallback pra
      // refresh/deep-link direto.
      let it: SocialActivity | null = null;
      let own: string | null = null;
      try {
        const raw = sessionStorage.getItem("rm_friend_activity");
        if (raw) { it = JSON.parse(raw); sessionStorage.removeItem("rm_friend_activity"); }
      } catch { /* ok */ }

      const q = new URLSearchParams(window.location.search);
      own = it?.owner ?? q.get("owner");
      setOwner(own);

      // sem o item em mãos (deep-link/refresh): rebusca a lista do dono e acha pela key
      if (!it && own) {
        const key = q.get("key");
        const acts = await getAthleteActivities(own);
        it = acts?.find((a) => a.key === key) ?? null;
      }

      setItem(it);
      setLoading(false);

      if (it && own && it.has_photo) getActivityPhoto(it.key, own).then(setPhotoUrl).catch(() => {});

      if (it && own && it.has_track) {
        setLoadingTrack(true);
        setTrack(await getTrack(it, own));
        setLoadingTrack(false);
      }
    })();
  }, []);

  async function onKudos() {
    if (!item) return;
    const liked = await toggleKudos(item.owner, item.key);
    setItem({ ...item, kudos_by_me: liked, kudos: item.kudos + (liked ? 1 : -1) });
  }

  if (loading) {
    return (
      <main className="stage"><div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
        <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
      </div></main>
    );
  }

  if (!item) {
    return (
      <main className="stage"><div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.back()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Atividade</div></div>
          <span style={{ width: 34 }} />
        </header>
        <div className="card center"><p className="muted" style={{ margin: 0 }}>Atividade não encontrada.</p></div>
      </div></main>
    );
  }

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => owner ? router.push(`/atleta?id=${owner}`) : router.back()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title">
            <div className="k">{fmtDate(item.datetime ?? item.date_iso)}</div>
            <div className="t">{item.owner_name ? `${item.owner_name} · ${item.name}` : item.name}</div>
          </div>
          <button className={`icon-btn kudos${item.kudos_by_me ? " on" : ""}`} aria-label="Kudos" onClick={onKudos}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill={item.kudos_by_me ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-6 0v4H5l1.5 10.5A2 2 0 0 0 8.5 21h7a2 2 0 0 0 2-1.5L19 9z" /></svg>
          </button>
        </header>

        {item.kudos > 0 && (
          <p className="muted" style={{ margin: "0 2px 2px", fontSize: 13 }}>
            👏 {item.kudos} {item.kudos === 1 ? "kudo" : "kudos"}
          </p>
        )}

        <ActivityDetailBody item={item} track={track} loadingTrack={loadingTrack} photoUrl={photoUrl} />
      </div>
    </main>
  );
}

export default function AtividadeAmigoPage() {
  return (
    <Suspense fallback={
      <main className="stage"><div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
        <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
      </div></main>
    }>
      <AtividadeAmigoInner />
    </Suspense>
  );
}
