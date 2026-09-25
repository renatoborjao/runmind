"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import PasswordField from "../password-field";
import { getMe, getMySocial, getProfile, logout, saveProfile, setMySocial, setPassword, stravaConnectUrl, type Me, type MySocial, type Profile } from "@/lib/api";

function SocialSettings() {
  const [s, setS] = useState<MySocial | null>(null);
  const [bio, setBio] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => { (async () => { const d = await getMySocial(); if (d) { setS(d); setBio(d.bio); } })(); }, []);

  async function setPrivacy(privacy: "public" | "private") {
    const d = await setMySocial({ privacy });
    if (d) setS(d);
  }
  async function saveBio() {
    const d = await setMySocial({ bio });
    if (d) { setS(d); setSaved(true); setTimeout(() => setSaved(false), 2000); }
  }
  if (!s) return null;

  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Social</span></div>
      <p className="muted" style={{ margin: "0 0 10px", fontSize: 12.5 }}>Quem pode te seguir e ver suas atividades:</p>
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={s.privacy === "public" ? "on" : ""} onClick={() => setPrivacy("public")}>Público</button>
        <button className={s.privacy === "private" ? "on" : ""} onClick={() => setPrivacy("private")}>Com solicitação</button>
      </div>
      <p className="muted" style={{ margin: "0 0 6px", fontSize: 11.5 }}>
        {s.privacy === "public" ? "Qualquer atleta segue na hora e vê suas corridas." : "Seguir precisa da sua aprovação; só aprovados veem suas corridas."}
      </p>
      <label className="field" style={{ marginTop: 8 }}>
        <span>Bio</span>
        <input value={bio} maxLength={280} onChange={(e) => setBio(e.target.value)} placeholder="Uma linha sobre você (opcional)" />
      </label>
      <button className="btn-ghost" style={{ marginTop: 8 }} onClick={saveBio}>{saved ? "Salvo ✓" : "Salvar bio"}</button>
      <p className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>{s.followers} seguidores · {s.following} seguindo</p>
    </section>
  );
}

const SEX_PT: Record<string, string> = { M: "Masculino", F: "Feminino" };

// Lê a foto escolhida e devolve um data URL leve: recorta quadrado central e
// reduz pra 256px em JPEG — fica com poucos KB, sem precisar de upload/servidor.
function fileToAvatar(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("img"));
      img.onload = () => {
        const S = 256;
        const canvas = document.createElement("canvas");
        canvas.width = S; canvas.height = S;
        const ctx = canvas.getContext("2d");
        if (!ctx) { reject(new Error("ctx")); return; }
        const side = Math.min(img.width, img.height);
        const sx = (img.width - side) / 2;
        const sy = (img.height - side) / 2;
        ctx.drawImage(img, sx, sy, side, side, 0, 0, S, S);
        resolve(canvas.toDataURL("image/jpeg", 0.82));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

// Conexões: Strava o próprio atleta conecta daqui (OAuth). Garmin ainda é
// liberado pela gente enquanto a Garmin não abre a conexão oficial.
function Connections({ p, result }: { p: Profile; result: string | null }) {
  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Conexões</span></div>
      {result === "ok" && <p className="notice ok" style={{ margin: "0 0 10px" }}>✅ Strava conectado! Vou ler seu histórico e ajustar seu plano — te aviso no coach.</p>}
      {result === "erro" && <p className="notice err" style={{ margin: "0 0 10px" }}>Não consegui conectar o Strava. Tenta de novo.</p>}
      <div className="prow">
        <span className="pl">Strava</span>
        {p.strava_connected ? (
          <span className="pv">Conectado ✓ · <a className="link" href={stravaConnectUrl("perfil")}>reconectar</a></span>
        ) : (
          <span className="pv muted">Não conectado</span>
        )}
      </div>
      {!p.strava_connected && (
        <a className="btn btn-strava" href={stravaConnectUrl("perfil")} style={{ marginTop: 10 }}>Conectar com Strava</a>
      )}
      <div className="prow">
        <span className="pl">Garmin</span>
        <span className="pv">{p.garmin_connected ? "Conectado ✓" : <span className="muted">Em breve</span>}</span>
      </div>
    </section>
  );
}

// Acesso: a senha é o que garante voltar ao app sem Telegram/e-mail — quem
// entrou por código do coach ou Google pode criar uma aqui.
function AccessSettings() {
  const [me, setMe] = useState<Me | null>(null);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { (async () => setMe(await getMe()))(); }, []);
  if (!me) return null;

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    const res = await setPassword(next, me!.has_password ? current : undefined);
    setSaving(false);
    if (!res.ok) { setMsg({ ok: false, text: res.error || "Não consegui salvar." }); return; }
    setMe({ ...me!, has_password: true });
    setOpen(false);
    setCurrent("");
    setNext("");
    setMsg({ ok: true, text: "Senha salva! ✅ Agora é só entrar com teu e-mail e senha." });
  }

  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Acesso</span></div>
      <div className="prow">
        <span className="pl">E-mail de login</span>
        <span className="pv">{me.email || "—"}</span>
      </div>
      <div className="prow">
        <span className="pl">Senha</span>
        <span className="pv">
          {me.has_password ? "Criada ✓" : <span className="muted">Não criada</span>}
          {" · "}
          <a className="link" onClick={() => { setOpen((o) => !o); setMsg(null); }}>
            {me.has_password ? "trocar" : "criar"}
          </a>
        </span>
      </div>
      <div className="prow">
        <span className="pl">Google</span>
        <span className="pv">{me.google_linked ? "Conectado ✓" : <span className="muted">Não conectado</span>}</span>
      </div>
      {!me.email && !me.has_password && (
        <p className="muted" style={{ margin: "8px 2px 0", fontSize: 12 }}>
          Cadastra teu e-mail em <b>Dados</b> pra poder entrar com senha.
        </p>
      )}
      {open && (
        <form onSubmit={onSave} style={{ marginTop: 10 }}>
          {me.has_password && (
            <PasswordField id="curpw" label="Senha atual" value={current} onChange={setCurrent} autoComplete="current-password" />
          )}
          <PasswordField id="newpw" label="Senha nova (mín. 8 caracteres)" value={next} onChange={setNext} autoComplete="new-password" />
          <button className="btn" type="submit" disabled={saving || next.length < 8 || !me.email}>
            {saving ? "Salvando…" : "Salvar senha"}
          </button>
        </form>
      )}
      {msg && <p className={`notice ${msg.ok ? "ok" : "err"}`} style={{ margin: "10px 0 0" }}>{msg.text}</p>}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="prow">
      <span className="pl">{label}</span>
      <span className="pv">{value}</span>
    </div>
  );
}

type Form = {
  first_name: string;
  last_name: string;
  email: string;
  age: string;
  weight: string;
  height: string;
  sex: string;
  avatar: string; // data URL ou "" (sem foto)
};

function toForm(p: Profile): Form {
  return {
    first_name: p.first_name ?? "",
    last_name: p.last_name ?? "",
    email: p.email ?? "",
    age: p.age ? String(p.age) : "",
    weight: p.weight ? String(p.weight) : "",
    height: p.height ? String(p.height) : "",
    sex: p.sex ?? "",
    avatar: p.avatar ?? "",
  };
}

export default function PerfilPage() {
  const router = useRouter();
  const [p, setP] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [stravaResult, setStravaResult] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      // volta do Strava: ?strava=ok|erro (lê e limpa a URL)
      const result = new URLSearchParams(window.location.search).get("strava");
      if (result) { setStravaResult(result); router.replace("/perfil"); }
      const data = await getProfile();
      if (!data) { router.replace("/entrar"); return; }
      setP(data);
      setLoading(false);
    })();
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/entrar");
  }

  function startEdit() {
    if (!p) return;
    setF(toForm(p));
    setErr(null);
    setEditing(true);
  }

  async function onSave() {
    if (!f) return;
    setSaving(true); setErr(null);
    const res = await saveProfile({
      first_name: f.first_name.trim(),
      last_name: f.last_name.trim(),
      email: f.email.trim() || null,
      age: f.age ? Number(f.age) : undefined,
      weight: f.weight ? Number(f.weight.replace(",", ".")) : undefined,
      height: f.height ? Number(f.height.replace(",", ".")) : undefined,
      sex: f.sex || null,
      avatar: f.avatar,
    });
    setSaving(false);
    if (!res.ok) { setErr(res.message ?? "Não consegui salvar."); return; }
    if (res.profile) setP(res.profile);
    setEditing(false);
  }

  if (loading || !p) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // TELA: editar dados pessoais
  if (editing && f) {
    const up = (patch: Partial<Form>) => setF((s) => (s ? { ...s, ...patch } : s));
    return (
      <main className="stage">
        <div className="phone">
          <header className="appbar">
            <button className="icon-btn" aria-label="Voltar" onClick={() => { setEditing(false); setErr(null); }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <div className="title"><div className="t">Editar dados</div></div>
            <span style={{ width: 34 }} />
          </header>

          {err && <div className="notice err">{err}</div>}

          <div className="card" style={{ padding: 16 }}>
            <input ref={fileRef} type="file" accept="image/*" hidden
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                try {
                  const av = await fileToAvatar(file);
                  up({ avatar: av });
                } catch {
                  setErr("Não consegui ler essa imagem. Tenta outra.");
                }
              }} />

            <div className="avatar-edit">
              {f.avatar ? (
                <img className="avatar-preview" src={f.avatar} alt="Foto do perfil" />
              ) : (
                <span className="avatar-lg">{(f.first_name?.[0] ?? "") + (f.last_name?.[0] ?? "") || "🏃"}</span>
              )}
              <div className="avatar-actions">
                <button type="button" className="btn-ghost" onClick={() => fileRef.current?.click()}>
                  {f.avatar ? "Trocar foto" : "Adicionar foto"}
                </button>
                {f.avatar && (
                  <button type="button" className="btn-ghost danger" onClick={() => up({ avatar: "" })}>Remover</button>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Nome</label>
                <input value={f.first_name} onChange={(e) => up({ first_name: e.target.value })} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Sobrenome</label>
                <input value={f.last_name} onChange={(e) => up({ last_name: e.target.value })} />
              </div>
            </div>

            <div className="field" style={{ marginBottom: 12 }}>
              <label>E-mail (login)</label>
              <input type="email" value={f.email} onChange={(e) => up({ email: e.target.value })} placeholder="voce@email.com" />
            </div>

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Idade</label>
                <input type="number" inputMode="numeric" value={f.age} onChange={(e) => up({ age: e.target.value })} placeholder="anos" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Peso (kg)</label>
                <input type="number" inputMode="decimal" step="0.1" value={f.weight} onChange={(e) => up({ weight: e.target.value })} placeholder="kg" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Altura (m)</label>
                <input type="number" inputMode="decimal" step="0.01" value={f.height} onChange={(e) => up({ height: e.target.value })} placeholder="1,75" />
              </div>
            </div>

            <div>
              <label className="fld-label">Sexo</label>
              <div className="chips">
                {(["M", "F"] as const).map((s) => (
                  <button key={s} type="button" className={`chip-btn${f.sex === s ? " on" : ""}`}
                    onClick={() => up({ sex: f.sex === s ? "" : s })}>{SEX_PT[s]}</button>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button className="btn-ghost" style={{ flex: 1 }} disabled={saving} onClick={() => { setEditing(false); setErr(null); }}>Cancelar</button>
              <button className="btn-primary" style={{ flex: 1 }} disabled={saving} onClick={onSave}>{saving ? "Salvando…" : "Salvar"}</button>
            </div>
          </div>

          <p className="muted center" style={{ marginTop: 4, fontSize: 12 }}>
            Meta, dias de treino e prova você ajusta conversando com o coach 💬
          </p>
        </div>
      </main>
    );
  }

  const initials = (p.first_name?.[0] ?? "") + (p.last_name?.[0] ?? "");

  return (
    <main className="stage">
      <div className="phone">

        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Perfil</div></div>
          <span style={{ width: 34 }} />
        </header>

        {/* cabeçalho */}
        <section className="card" style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {p.avatar ? (
            <img className="avatar-preview sm" src={p.avatar} alt="Foto do perfil" />
          ) : (
            <span className="avatar-lg">{initials || "🏃"}</span>
          )}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 20 }}>{p.name}</div>
            {p.email && <div className="muted" style={{ fontSize: 13 }}>{p.email}</div>}
          </div>
        </section>

        {/* dados pessoais */}
        <section className="card">
          <div className="card-head">
            <span className="eyebrow">Dados</span>
            <a className="link" onClick={startEdit}>Editar</a>
          </div>
          <Row label="Nome" value={p.first_name || "—"} />
          <Row label="Sobrenome" value={p.last_name || "—"} />
          <Row label="E-mail" value={p.email || "—"} />
          <Row label="Idade" value={p.age ? `${p.age} anos` : "—"} />
          <Row label="Peso" value={p.weight ? `${String(p.weight).replace(".", ",")} kg` : "—"} />
          <Row label="Altura" value={p.height ? `${String(p.height).replace(".", ",")} m` : "—"} />
          <Row label="Sexo" value={p.sex ? (SEX_PT[p.sex] ?? p.sex) : "—"} />
        </section>

        {/* treino */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Treino</span></div>
          <Row label="Objetivo" value={p.goal || "—"} />
          <Row label="Dias por semana" value={p.weekly_training_days ? `${p.weekly_training_days}x` : "—"} />
          <Row label="Dias preferidos" value={p.preferred_running_days.length ? p.preferred_running_days.join(", ") : "—"} />
          <p className="muted" style={{ margin: "10px 2px 0", fontSize: 12 }}>Isso é dinâmico — ajuste com o coach. 💬</p>
        </section>

        <Connections p={p} result={stravaResult} />

        <AccessSettings />

        {/* provas */}
        <section className="card tap" onClick={() => router.push("/provas")}>
          <div className="card-head"><span className="eyebrow">Minhas provas</span></div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <div style={{ minWidth: 0 }}>
              {p.target_race ? (
                <>
                  <div style={{ fontWeight: 700, fontSize: 14.5 }}>{p.target_race}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    {p.race_date ? new Date(p.race_date + "T00:00:00").toLocaleDateString("pt-BR") : ""}
                    {p.target_time ? ` · alvo ${p.target_time}` : ""}
                  </div>
                </>
              ) : (
                <div className="muted" style={{ fontSize: 13 }}>Cadastre uma ou mais provas 🏁</div>
              )}
            </div>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="var(--muted)" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none" }}><path d="M9 18l6-6-6-6" /></svg>
          </div>
        </section>

        <SocialSettings />

        <button className="btn-danger" onClick={onLogout}>Sair da conta</button>

        <p className="muted center" style={{ marginTop: 4 }}>Ritmind</p>

      </div>
    </main>
  );
}
