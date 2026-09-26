// Cliente da API do Ritmind. Todas as chamadas mandam o cookie de sessão
// (credentials: "include") — é assim que o backend sabe quem é o atleta.

// PRODUÇÃO é SEMPRE relativa (/api/v1 na mesma origem — o Caddy faz o proxy).
// Nunca lê env no build de produção: um build que herdou o .env.local de dev
// saiu apontando pra localhost:8000 e derrubou o app de todo mundo (2026-09-23).
// Só o `next dev` usa a URL do .env.local / localhost.
const API_BASE =
  process.env.NODE_ENV === "production"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

// Marca de build visível no app (rodapé da home) — pra confirmar rápido qual
// versão está de fato rodando no aparelho quando o cache do PWA teima. Bump a
// cada deploy junto com o service worker.
export const APP_BUILD = "b26 · sticker parciais + dados";

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

export interface Me {
  profile: string;
  name: string;
  email: string | null;
  goal: string;
  onboarding_complete: boolean;
  has_password?: boolean;
  google_linked?: boolean;
}

// erro legível da API ({"detail": "..."}), ou o genérico
async function apiError(r: Response, fallback: string): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch { /* mantém o genérico */ }
  return fallback;
}

/** Login por e-mail + senha. */
export async function loginWithPassword(email: string, password: string): Promise<{ ok: boolean; error?: string }> {
  const r = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (r.ok) return { ok: true };
  return { ok: false, error: await apiError(r, "Não consegui entrar agora. Tenta de novo.") };
}

/** Entrar com Google (credential = ID token do Google). Conta nova pede convite. */
export async function googleLogin(
  credential: string,
  inviteCode?: string,
): Promise<{ ok: boolean; needsInvite?: boolean; created?: boolean; error?: string }> {
  const r = await apiFetch("/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential, invite_code: inviteCode || null }),
  });
  if (!r.ok) return { ok: false, error: await apiError(r, "Não consegui entrar com o Google.") };
  const body = await r.json();
  if (body.needs_invite) return { ok: false, needsInvite: true };
  return { ok: true, created: !!body.created };
}

/** Configuração da tela de login (Client ID do Google, se ligado). */
export async function getAuthConfig(): Promise<{ google_client_id: string | null }> {
  try {
    const r = await apiFetch("/auth/config");
    if (r.ok) return r.json();
  } catch { /* sem config: só e-mail/senha */ }
  return { google_client_id: null };
}

/** Cria (1ª vez) ou troca a senha do atleta logado. */
export async function setPassword(newPassword: string, currentPassword?: string): Promise<{ ok: boolean; error?: string }> {
  const r = await apiFetch("/auth/password", {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword, current_password: currentPassword || null }),
  });
  if (r.ok) return { ok: true };
  return { ok: false, error: await apiError(r, "Não consegui salvar a senha.") };
}

/** Senha nova com a permissão que o link/código de acesso entrega. */
export async function resetPassword(resetToken: string, newPassword: string): Promise<{ ok: boolean; error?: string }> {
  const r = await apiFetch("/auth/password/reset", {
    method: "POST",
    body: JSON.stringify({ reset_token: resetToken, new_password: newPassword }),
  });
  if (r.ok) return { ok: true };
  return { ok: false, error: await apiError(r, "Não consegui salvar a senha.") };
}

/** Pede o magic link. Resposta sempre genérica (não revela se o e-mail existe). */
export async function requestLogin(email: string): Promise<boolean> {
  const r = await apiFetch("/auth/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  return r.ok;
}

/**
 * Auto-cadastro por convite. Convite válido de atleta NOVO já loga (`loggedIn`);
 * e-mail que já tem conta volta `loggedIn:false` (o app manda pra tela Entrar).
 */
export async function signup(
  email: string,
  inviteCode: string,
  password: string,
): Promise<{ ok: boolean; loggedIn?: boolean; message?: string; error?: string }> {
  const r = await apiFetch("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, invite_code: inviteCode, password }),
  });
  if (r.ok) {
    try {
      const body = await r.json();
      return { ok: true, loggedIn: !!body?.logged_in, message: body?.message };
    } catch {
      return { ok: true, loggedIn: false };
    }
  }
  let error = "Não consegui te cadastrar. Confere o convite e tenta de novo.";
  try {
    const body = await r.json();
    if (body?.detail) error = body.detail;
  } catch {
    /* mantém o genérico */
  }
  return { ok: false, error };
}

/** Payload do wizard de onboarding (dados estruturados). */
export interface OnboardingPayload {
  name: string;
  age: number;
  sex: "M" | "F" | null;
  weight: number;
  height: number;
  days: number[]; // 0=segunda .. 6=domingo
  goal: string;
  target_race?: string | null;
  target_time?: string | null;
  race_date?: string | null;
  runs_today: boolean;
  runs_per_week?: number | null;
  typical_km?: number | null;
  pace_distance_km?: number | null;
  pace_minutes?: number | null;
  mobility?: "walker" | "run_walker" | "runner" | null;
  continuous_run_minutes?: number | null;
  walk_speed_kmh?: number | null;
  external_coach: boolean;
}

/** Conclui o onboarding no app: grava o perfil e gera o plano. */
export async function completeOnboarding(
  payload: OnboardingPayload,
): Promise<{ ok: boolean; error?: string }> {
  const r = await apiFetch("/onboarding/complete", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (r.ok) return { ok: true };
  let error = "Não consegui finalizar. Confere os dados e tenta de novo.";
  try {
    const body = await r.json();
    if (body?.detail) error = body.detail;
  } catch {
    /* mantém o genérico */
  }
  return { ok: false, error };
}

/** Troca o magic token pela sessão (seta o cookie). */
/** Troca link/código de acesso por sessão. Devolve a permissão de redefinir
 *  a senha (15 min) — quem entrou por link provou que é o dono. */
export async function verifyToken(token: string): Promise<{ resetToken: string; hasPassword: boolean } | null> {
  const r = await apiFetch("/auth/verify", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  if (!r.ok) return null;
  const body = await r.json();
  return { resetToken: body.reset_token, hasPassword: !!body.has_password };
}

/** Quem está logado? null se não há sessão válida. */
export async function getMe(): Promise<Me | null> {
  const r = await apiFetch("/auth/me");
  if (!r.ok) return null;
  return r.json();
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

export interface PlanSession {
  day: string;
  workout_type: string;
  objective?: string;
  target_pace_min?: string | null;
  target_pace_max?: string | null;
}

export interface PlanResponse {
  plan?: { sessions?: PlanSession[] };
}

export async function getPlan(): Promise<PlanResponse | null> {
  const r = await apiFetch("/plan");
  if (!r.ok) return null;
  return r.json();
}

// ---- Home ----

export interface WorkoutStep {
  kind: string;
  distance_m: number | null;
  duration_sec: number | null;
  pace_min: string | null;
  pace_max: string | null;
  reps: number | null;
  steps?: WorkoutStep[];
}

export interface TodaySession {
  workout_type: string;
  objective: string;
  distance_km: number | null;
  duration_min: number | null;
  pace_min: string | null;
  pace_max: string | null;
  kind: string;
  steps: WorkoutStep[];
}

export interface WeekDay {
  day_en: string;
  day_pt: string;
  date_num: number;
  date_iso: string;
  workout_type: string | null;
  distance_km: number | null;
  kind: string | null;
  is_today: boolean;
  done: boolean;
}

export interface HomeSummary {
  athlete: { name: string; goal: string; avatar?: string | null };
  today: {
    weekday_pt: string;
    date_label: string;
    label: string;
    day_en: string;
    session_date_label: string | null;
    session: TodaySession | null;
  };
  week: WeekDay[];
  body: {
    ring: { value: number; label: string; source: string } | null;
    readiness_score: number | null;
    readiness_level: string | null;
    sleep_hours: number | null;
    resting_hr: number | null;
    respiration_sleep_avg: number | null;
    body_battery_at_wake: number | null;
    steps: number | null;
    active_calories: number | null;
    spo2_sleep_avg: number | null;
    training_status: string | null;
    date: string;
  } | null;
  fitness: {
    vo2max: number | null;
    projection_10k: string | null;
    projection_5k: string | null;
    projection_half: string | null;
  } | null;
  shoe: {
    name: string;
    total_km: number;
    alert_threshold_km: number;
    pct: number;
    remaining_km: number;
  } | null;
}

export async function getHome(): Promise<HomeSummary | null> {
  const r = await apiFetch("/home");
  if (!r.ok) return null;
  return r.json();
}

// ---- Workouts (calendário/lista) ----

export interface WorkoutDay {
  day_en: string;
  day_pt: string;
  date_iso: string;
  date_num: number;
  is_today: boolean;
  is_past: boolean;
  session: TodaySession | null;
}

export interface RaceInfo {
  name: string;
  date_iso: string;
  target_time: string | null;
  days_until: number;
}

export interface WorkoutsResponse {
  week: WorkoutDay[];
  race: RaceInfo | null;
  garmin_connected?: boolean;
  watch_day_closed?: boolean;
}

export async function getWorkouts(): Promise<WorkoutsResponse | null> {
  const r = await apiFetch("/workouts");
  if (!r.ok) return null;
  return r.json();
}

// ---- Calendário (mês + histórico + comparação) ----

export interface CalExecuted {
  date_iso: string;
  km: number;
  pace: string | null;
  duration_min: number;
  name: string;
  kind: string;
  is_ours: boolean;
}

export interface CalPlanned {
  date_iso: string;
  day_en: string;
  workout_type: string;
  kind: string;
}

export interface CalendarMonth {
  month: string;
  executed: CalExecuted[];
  planned: CalPlanned[];
  race: RaceInfo | null;
}

export async function getCalendar(year: number, month: number): Promise<CalendarMonth | null> {
  const r = await apiFetch(`/calendar?year=${year}&month=${month}`);
  if (!r.ok) return null;
  return r.json();
}

export interface DayDetail {
  date_iso: string;
  day_pt: string;
  executed: {
    km: number;
    pace: string | null;
    duration_min: number;
    avg_hr: number | null;
    elevation_gain: number | null;
    name: string;
    is_ours: boolean;
  } | null;
  planned: {
    workout_type: string;
    distance_km: number | null;
    pace_min: string | null;
    pace_max: string | null;
    kind: string;
  } | null;
}

export async function getDayDetail(dateIso: string): Promise<DayDetail | null> {
  const r = await apiFetch(`/calendar/day?date=${dateIso}`);
  if (!r.ok) return null;
  return r.json();
}

// ---- Coach (chat nativo) ----

export interface ChatMsg {
  role: string; // "user" | "assistant" | "coach" (proativo)
  text: string;
  at: string | null;
  kind?: string | null;
  title?: string | null;
  url?: string | null;
  image_url?: string | null;   // foto que o atleta mandou (servida pela API)
  local_image?: string | null; // prévia local (data URL) antes do servidor responder
}

// URL absoluta de uma mídia servida pela API (em produção é relativa).
export function apiMediaSrc(path: string): string {
  return `${API_BASE}${path}`;
}

export async function getCoachMessages(): Promise<ChatMsg[] | null> {
  const r = await apiFetch("/coach/messages");
  if (!r.ok) return null;
  const data = await r.json();
  return data.messages ?? [];
}

export async function sendCoachMessage(text: string): Promise<string | null> {
  const r = await apiFetch("/coach/messages", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (!r.ok) return null;
  const data = await r.json();
  return data.reply ?? null;
}

// Foto (ou PDF) pro coach — `data` é data URL. O coach VÊ a imagem e responde.
export async function sendCoachPhoto(data: string, caption: string): Promise<string | null> {
  const r = await apiFetch("/coach/photo", {
    method: "POST",
    body: JSON.stringify({ data, caption }),
  });
  if (!r.ok) return null;
  const d = await r.json();
  return d.reply ?? null;
}

// Áudio pro coach — transcreve no servidor e segue como mensagem.
export async function sendCoachVoice(
  data: string,
  duration: number,
): Promise<{ transcript: string | null; reply: string } | null> {
  const r = await apiFetch("/coach/voice", {
    method: "POST",
    body: JSON.stringify({ data, duration }),
  });
  if (!r.ok) return null;
  return r.json();
}

// ---- Evolução (progresso) ----

export interface Progress {
  journey: { km_total: number; runs: number; biggest_km: number; since: string | null };
  weekly_volume: { label: string; km: number }[];
  fitness: {
    vo2max: number | null;
    vo2max_trend?: "up" | "down" | "flat" | null;
    resting_hr: number | null;
    resting_hr_trend?: "up" | "down" | "flat" | null;
    hrv?: number | null;
    hrv_trend?: "up" | "down" | "flat" | null;
    hrv_status?: string | null;
    training_status?: string | null;
    projection_5k: string | null;
    projection_10k: string | null;
    projection_half: string | null;
    projection_marathon: string | null;
  };
}

export async function getProgress(): Promise<Progress | null> {
  const r = await apiFetch("/progress");
  if (!r.ok) return null;
  return r.json();
}

// ---- Perfil ----

export interface Profile {
  id: string;
  first_name: string;
  last_name: string;
  name: string;
  email: string | null;
  age: number;
  weight: number;
  height: number;
  sex: string | null;
  avatar: string | null;
  timezone: string;
  goal: string;
  weekly_training_days: number;
  preferred_running_days: string[];
  target_race: string | null;
  race_date: string | null;
  target_time: string | null;
  strava_connected: boolean;
  garmin_connected: boolean;
}

// Conectar o Strava pelo app: navegação de página inteira (não fetch) — o
// backend lê o cookie de sessão, manda pro Strava e devolve o atleta pra tela
// de origem com `?strava=ok|erro`.
export function stravaConnectUrl(back: "perfil" | "onboarding"): string {
  return `${API_BASE}/api/v1/strava/app-connect?back=${back}`;
}

export async function getProfile(): Promise<Profile | null> {
  const r = await apiFetch("/profile");
  if (!r.ok) return null;
  return r.json();
}

export interface ProfilePatch {
  first_name?: string;
  last_name?: string;
  email?: string | null;
  age?: number;
  weight?: number;
  height?: number;
  sex?: string | null;
  avatar?: string | null;
}

export async function saveProfile(body: ProfilePatch): Promise<{ ok: boolean; profile?: Profile; message?: string }> {
  const r = await apiFetch("/profile", { method: "PATCH", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: data.detail || "Não consegui salvar." };
  return { ok: true, profile: data };
}

// ---- Corrida gravada (GPS no app) ----

export interface RunPayload {
  started_at: string;
  duration_s: number;
  distance_m: number;
  avg_pace: string | null;
  points: { lat: number; lon: number; t: number }[];
}

export async function saveRun(run: RunPayload): Promise<boolean> {
  const r = await apiFetch("/recorded-runs", {
    method: "POST",
    body: JSON.stringify(run),
  });
  return r.ok;
}

export interface RecordedRunSummary {
  id: string;
  saved_at: string | null;
  started_at: string | null;
  duration_s: number;
  distance_m: number;
  avg_pace: string | null;
}

export interface RunSplit {
  km: number | null;
  sec: number;
  pace: string | null;
  partial_km: number | null;
  hr?: number | null;
}

export interface RecordedRunDetail extends RecordedRunSummary {
  points: { lat: number; lon: number; t: number | null }[];
  splits: RunSplit[];
}

export async function getRecordedRuns(): Promise<RecordedRunSummary[] | null> {
  const r = await apiFetch("/recorded-runs");
  if (!r.ok) return null;
  const data = await r.json();
  return data.runs ?? [];
}

export async function getRecordedRun(id: string): Promise<RecordedRunDetail | null> {
  const r = await apiFetch(`/recorded-runs/${id}`);
  if (!r.ok) return null;
  return r.json();
}

// ---- Feed de atividades (todas as corridas) ----

export interface FeedItem {
  key: string;
  source: "app" | "sync";
  datetime: string | null;
  date_iso: string;
  distance_km: number;
  duration_min: number;
  duration_s: number;
  pace: string | null;
  avg_hr: number | null;
  max_hr: number | null;
  elevation_gain: number | null;
  hr_zones: number[] | null;
  hr_zone_floors?: number[] | null;
  air_temp_c: number | null;
  name: string;
  has_track: boolean;
  track_source: "app" | "arch" | null;
  track_id: string | null;
  route_preview?: [number, number][] | null;
  custom_title?: boolean;
  has_photo?: boolean;
  comment_count?: number;
}

export interface ActivityComment {
  id: string;
  author: string;
  author_name: string;
  text: string;
  at: string;
}

/** Comentários de uma atividade + o meu id (pra saber o que posso apagar). */
export async function getComments(key: string, owner?: string): Promise<{ comments: ActivityComment[]; me: string } | null> {
  const q = owner ? `?owner=${owner}&key=${encodeURIComponent(key)}` : `?key=${encodeURIComponent(key)}`;
  const r = await apiFetch(`/feed/comments${q}`);
  return r.ok ? r.json() : null;
}

export async function addComment(key: string, text: string, owner?: string): Promise<ActivityComment | null> {
  const r = await apiFetch("/feed/comments", { method: "POST", body: JSON.stringify({ key, text, owner }) });
  return r.ok ? (await r.json()).comment : null;
}

export async function deleteComment(key: string, id: string, owner?: string): Promise<boolean> {
  const q = owner ? `?owner=${owner}&key=${encodeURIComponent(key)}&id=${id}` : `?key=${encodeURIComponent(key)}&id=${id}`;
  const r = await apiFetch(`/feed/comments${q}`, { method: "DELETE" });
  return r.ok;
}

/** Batiza uma atividade minha (título vazio remove o custom). */
export async function setActivityTitle(key: string, title: string): Promise<boolean> {
  const r = await apiFetch("/feed/meta", { method: "POST", body: JSON.stringify({ key, title }) });
  return r.ok;
}

/** Sobe 1 foto (data URL já comprimida no cliente) pra uma atividade minha. */
export async function uploadActivityPhoto(key: string, data: string): Promise<boolean> {
  const r = await apiFetch("/feed/photo", { method: "POST", body: JSON.stringify({ key, data }) });
  return r.ok;
}

export async function deleteActivityPhoto(key: string): Promise<boolean> {
  const r = await apiFetch(`/feed/photo/${encodeURIComponent(key)}`, { method: "DELETE" });
  return r.ok;
}

/** Foto de uma atividade como data URL. Sem `owner` = a minha. */
export async function getActivityPhoto(key: string, owner?: string): Promise<string | null> {
  const q = owner ? `?owner=${owner}&key=${encodeURIComponent(key)}` : `?key=${encodeURIComponent(key)}`;
  const r = await apiFetch(`/feed/photo${q}`);
  return r.ok ? (await r.json()).photo : null;
}

export async function getFeed(): Promise<FeedItem[] | null> {
  const r = await apiFetch("/feed");
  if (!r.ok) return null;
  const data = await r.json();
  return data.activities ?? [];
}

export interface ActivityMetrics {
  calories?: number;
  avg_cadence?: number;
  max_cadence?: number;
  avg_power?: number;
  max_power?: number;
  ground_contact_ms?: number;
  stride_length_cm?: number;
  vertical_oscillation_cm?: number;
  vertical_ratio?: number;
  elevation_loss?: number;
  avg_temperature?: number;
  steps?: number;
  training_effect?: number;
  anaerobic_effect?: number;
  training_effect_label?: string;
}

export interface ActivitySeries {
  dist: number[];
  hr: (number | null)[];
  elev: (number | null)[];
  pace: (number | null)[];
}

export interface TrackData {
  points: { lat: number; lon: number; t?: number | null }[];
  splits: RunSplit[];
  metrics?: ActivityMetrics | null;
  series?: ActivitySeries | null;
}

/** Traçado de uma atividade do feed — app (recorded-runs) ou sincronizada (feed/track).
 * `owner` (opcional) busca o traçado de OUTRO atleta via rota social. */
export async function getTrack(item: FeedItem, owner?: string): Promise<TrackData | null> {
  if (!item.has_track || !item.track_id) return null;
  if (owner) {
    const r = await apiFetch(`/social/athletes/${owner}/track/${item.track_source}/${item.track_id}`);
    return r.ok ? r.json() : null;
  }
  if (item.track_source === "app") {
    const d = await getRecordedRun(item.track_id);
    return d ? { points: d.points, splits: d.splits } : null;
  }
  const r = await apiFetch(`/feed/track/${item.track_id}`);
  if (!r.ok) return null;
  return r.json();
}

// ---- Análise do coach de um treino ----

export interface CoachAnalysis {
  analysis: string | null;
  workout_type?: string | null;
  created_at?: string | null;
}

/** Análise que o coach fez do treino daquele dia. Casa por data (+ distância),
 * igual ao dedup do feed. `analysis` vem null quando ainda não há análise. */
export async function getActivityAnalysis(item: FeedItem): Promise<CoachAnalysis | null> {
  const r = await apiFetch(
    `/feed/analysis?date=${encodeURIComponent(item.date_iso)}&km=${item.distance_km}`,
  );
  if (!r.ok) return null;
  return r.json();
}

// ---- Social (seguir, perfis, feed, kudos) ----

export type Relationship = "self" | "following" | "requested" | "none";

export interface AthleteCard {
  id: string;
  name: string;
  avatar: string | null;
  privacy: "public" | "private";
  relationship: Relationship;
}

export interface AthleteProfile extends AthleteCard {
  bio: string;
  counts: { following: number; followers: number };
  follows_me: boolean;
  can_view: boolean;
  journey: { km_total: number; runs: number; biggest_km: number } | null;
}

export interface SocialActivity extends FeedItem {
  owner: string;
  owner_name?: string;
  owner_avatar?: string | null;
  kudos: number;
  kudos_by_me: boolean;
}

export interface MySocial {
  privacy: "public" | "private";
  bio: string;
  following: number;
  followers: number;
}

export async function getAthletes(): Promise<AthleteCard[]> {
  const r = await apiFetch("/social/athletes");
  return r.ok ? (await r.json()).athletes : [];
}
export async function getAthlete(id: string): Promise<AthleteProfile | null> {
  const r = await apiFetch(`/social/athletes/${id}`);
  return r.ok ? r.json() : null;
}
export async function getAthleteActivities(id: string): Promise<SocialActivity[] | null> {
  const r = await apiFetch(`/social/athletes/${id}/activities`);
  if (r.status === 403) return null; // privado, sem acesso
  return r.ok ? (await r.json()).activities : [];
}
export async function getSocialFeed(): Promise<SocialActivity[]> {
  const r = await apiFetch("/social/feed");
  return r.ok ? (await r.json()).activities : [];
}
export async function followAthlete(id: string): Promise<Relationship> {
  const r = await apiFetch(`/social/follow/${id}`, { method: "POST" });
  return r.ok ? (await r.json()).relationship : "none";
}
export async function unfollowAthlete(id: string): Promise<void> {
  await apiFetch(`/social/unfollow/${id}`, { method: "POST" });
}
export async function getFollowRequests(): Promise<AthleteCard[]> {
  const r = await apiFetch("/social/requests");
  return r.ok ? (await r.json()).requests : [];
}
export async function acceptFollow(id: string): Promise<void> {
  await apiFetch(`/social/requests/${id}/accept`, { method: "POST" });
}
export async function rejectFollow(id: string): Promise<void> {
  await apiFetch(`/social/requests/${id}/reject`, { method: "POST" });
}
export async function toggleKudos(owner: string, key: string): Promise<boolean> {
  const r = await apiFetch("/social/kudos", { method: "POST", body: JSON.stringify({ owner, key }) });
  return r.ok ? (await r.json()).liked : false;
}
export async function getMySocial(): Promise<MySocial | null> {
  const r = await apiFetch("/social/me");
  return r.ok ? r.json() : null;
}
export async function setMySocial(patch: { privacy?: string; bio?: string }): Promise<MySocial | null> {
  const r = await apiFetch("/social/me", { method: "PUT", body: JSON.stringify(patch) });
  return r.ok ? r.json() : null;
}

// ---- Leitura do corpo ----

export interface BodyTrend {
  dates: string[];
  readiness: (number | null)[] | null;
  battery: (number | null)[] | null;
  sleep_hours: (number | null)[] | null;
  resting_hr: (number | null)[] | null;
  hrv: (number | null)[] | null;
}

export interface SleepNight {
  date: string;
  hours: number | null;
  score: number | null;
  deep: number | null;
  light: number | null;
  rem: number | null;
  awake: number | null;
}

export interface SleepDetail {
  date: string;
  hours: number | null;
  score: number | null;
  deep: number | null;
  light: number | null;
  rem: number | null;
  awake: number | null;
  respiration: number | null;
  spo2: number | null;
  nights?: SleepNight[];
}

export interface BodyReading {
  has_data: boolean;
  body_state?: string;
  state_label?: string;
  tone?: "good" | "warn" | "bad";
  limiter?: string | null;
  limiter_label?: string | null;
  narrative?: string | null;
  trend?: BodyTrend | null;
  sleep?: SleepDetail | null;
  acwr?: number | null;
  acwr_status?: string | null;
  recovery?: {
    hrv_recent: number | null;
    hrv_direction: string;
    rhr_recent: number | null;
    rhr_direction: string;
    sleep_avg_hours: number | null;
    short_nights: number;
    nights_counted: number;
    stress_avg: number | null;
    body_battery_wake: number | null;
    respiration_sleep: number | null;
    readiness_score: number | null;
    readiness_level: string | null;
    sleep_score: number | null;
  };
}

export async function getBody(): Promise<BodyReading | null> {
  const r = await apiFetch("/body");
  if (!r.ok) return null;
  return r.json();
}

// ---- Fortalecimento (biblioteca de exercícios pra quem corre) ----

export interface ExerciseExecution {
  sets: number;
  reps: number | null;
  hold_seconds: number | null;
  per_side: boolean;
  rest_seconds: number;
}

export interface StrengthExercise {
  id: string;
  name: string;
  category: string;
  target: string;
  equipment: string;
  why: string;
  cues: string[];
  reps: string;
  images: string[];
  common_mistake?: string | null;
  feel_where?: string | null;
  regression?: string | null;
  progression?: string | null;
  breathing?: string | null;
  execution?: ExerciseExecution | null;
}

export interface StrengthLibrary {
  categories: string[];
  exercises: StrengthExercise[];
  credit: string;
}

export async function getStrengthLibrary(): Promise<StrengthLibrary | null> {
  const r = await apiFetch("/strength/library");
  if (!r.ok) return null;
  return r.json();
}

export interface StrengthRoutineExercise extends StrengthExercise {
  sets: number;
  prescription: string;
}

export interface StrengthRoutine {
  days: string[];
  days_pt: string[];
  frequency: number;
  sets: number;
  note: string;
  exercises: StrengthRoutineExercise[];
}

export async function getStrengthRoutine(): Promise<StrengthRoutine | null> {
  const r = await apiFetch("/strength/routine");
  if (!r.ok) return null;
  return r.json();
}

// ---- Armário de tênis ----

export interface Shoe {
  id: string;
  name: string;
  nickname: string | null;
  label: string;
  category: string | null;
  is_default: boolean;
  retired: boolean;
  total_km: number;
  initial_km: number;
  accumulated_km: number;
  alert_threshold_km: number;
  pct: number;
  remaining_km: number;
  worn: boolean;
}

export interface ShoeInput {
  name: string;
  nickname?: string | null;
  category?: string | null;
  initial_km?: number | null;
  alert_threshold_km?: number | null;
  is_default?: boolean;
}

export interface ShoePatch {
  name?: string;
  nickname?: string | null;
  category?: string | null;
  total_km?: number | null;
  alert_threshold_km?: number | null;
  is_default?: boolean;
  retired?: boolean;
}

export async function getShoes(): Promise<Shoe[] | null> {
  const r = await apiFetch("/shoes");
  if (!r.ok) return null;
  const data = await r.json();
  return data.shoes ?? [];
}

export async function addShoe(body: ShoeInput): Promise<{ ok: boolean; shoe?: Shoe; message?: string }> {
  const r = await apiFetch("/shoes", { method: "POST", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: data.detail || "Não consegui adicionar." };
  return { ok: true, shoe: data };
}

export async function editShoe(id: string, body: ShoePatch): Promise<{ ok: boolean; shoe?: Shoe; message?: string }> {
  const r = await apiFetch(`/shoes/${id}`, { method: "PATCH", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: data.detail || "Não consegui salvar." };
  return { ok: true, shoe: data };
}

export async function deleteShoe(id: string): Promise<boolean> {
  const r = await apiFetch(`/shoes/${id}`, { method: "DELETE" });
  return r.ok;
}

// ---- Enviar plano pro relógio ----

export async function pushWatch(): Promise<{ ok: boolean; message: string }> {
  const r = await apiFetch("/plan/push-watch", { method: "POST" });
  if (!r.ok) return { ok: false, message: "Não consegui enviar agora. Tenta de novo." };
  return r.json();
}

// ---- Provas ----

export interface Race {
  id: string;
  name: string;
  date: string; // ISO YYYY-MM-DD
  target_time: string | null;
  is_anchor?: boolean;
  past?: boolean;
}

export async function getRaces(): Promise<Race[] | null> {
  const r = await apiFetch("/races");
  if (!r.ok) return null;
  const data = await r.json();
  return data.races ?? [];
}

export async function addRace(body: { name: string; date: string; target_time?: string | null }): Promise<{ ok: boolean; race?: Race; message?: string }> {
  const r = await apiFetch("/races", { method: "POST", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: data.detail || "Não consegui cadastrar." };
  return { ok: true, race: data.race };
}

export async function deleteRace(id: string): Promise<boolean> {
  const r = await apiFetch(`/races/${id}`, { method: "DELETE" });
  return r.ok;
}

// ---- Notificações (central no app) ----

export interface AppNotification {
  id: string;
  kind: string | null;
  title: string | null;
  text: string;
  created_at: string | null;
  read: boolean;
  url?: string | null;
}

export interface NotificationsResponse {
  items: AppNotification[];
  unread: number;
}

export async function getNotifications(): Promise<NotificationsResponse | null> {
  const r = await apiFetch("/notifications");
  if (!r.ok) return null;
  return r.json();
}

/** Marca notificações como lidas (todas, ou as `ids` informadas). Devolve o novo unread. */
export async function markNotificationsRead(ids?: string[]): Promise<number> {
  const r = await apiFetch("/notifications/read", {
    method: "POST",
    body: JSON.stringify(ids ? { ids } : {}),
  });
  if (!r.ok) return 0;
  const data = await r.json().catch(() => ({ unread: 0 }));
  return data.unread ?? 0;
}

// ---- Web Push (notificação no celular) ----

export async function getPushPublicKey(): Promise<string> {
  const r = await apiFetch("/push/public-key");
  if (!r.ok) return "";
  const data = await r.json().catch(() => ({ key: "" }));
  return data.key ?? "";
}

export async function subscribePush(sub: PushSubscriptionJSON): Promise<boolean> {
  const r = await apiFetch("/push/subscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint: sub.endpoint, keys: sub.keys }),
  });
  return r.ok;
}

export async function unsubscribePush(endpoint: string): Promise<boolean> {
  const r = await apiFetch("/push/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint }),
  });
  return r.ok;
}

// ---- Trocar treino de dia ----

export async function moveWorkout(
  fromDay: string,
  toDay: string,
): Promise<{ ok: boolean; message: string; watch?: "sent" | "late" | "failed" | "none" }> {
  const r = await apiFetch("/plan/move", {
    method: "POST",
    body: JSON.stringify({ from_day: fromDay, to_day: toDay }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: data.detail || "Não consegui trocar o dia." };
  return { ok: true, message: data.message || "Treino movido.", watch: data.watch };
}
