// Web Push no cliente: pede permissão, inscreve no push service do navegador com
// a nossa chave VAPID (vinda do backend) e registra a inscrição pra o servidor
// poder notificar. Tudo best-effort e defensivo — navegador sem suporte, chave
// ausente ou permissão negada nunca quebram o app.

import { getPushPublicKey, subscribePush, unsubscribePush } from "./api";

export type PushState = "unsupported" | "default" | "granted" | "denied";

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function pushState(): PushState {
  if (!pushSupported()) return "unsupported";
  return Notification.permission as PushState;
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/** Garante que este aparelho está inscrito e registrado no servidor. Só age se a
 *  permissão já foi concedida. Retorna true se ficou inscrito. */
export async function ensurePushSubscribed(): Promise<boolean> {
  if (!pushSupported() || Notification.permission !== "granted") return false;

  try {
    const key = await getPushPublicKey();
    if (!key) return false; // push desligado no servidor

    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();

    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
    }

    return await subscribePush(sub.toJSON() as PushSubscriptionJSON);
  } catch {
    return false;
  }
}

/** Pede a permissão e inscreve. Retorna o estado resultante. */
export async function requestPush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";

  try {
    const perm = await Notification.requestPermission();
    if (perm === "granted") await ensurePushSubscribed();
    return perm as PushState;
  } catch {
    return pushState();
  }
}

/** Desliga o push neste aparelho (remove a inscrição local e no servidor). */
export async function disablePush(): Promise<void> {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      const endpoint = sub.endpoint;
      await sub.unsubscribe().catch(() => {});
      await unsubscribePush(endpoint);
    }
  } catch {
    // silencioso
  }
}
