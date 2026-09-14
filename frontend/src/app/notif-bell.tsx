"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getNotifications } from "@/lib/api";
import { ensurePushSubscribed } from "@/lib/push";

// Sino da topbar: mostra o número de não-lidas e leva pra central. Também
// reinscreve o push silenciosamente quando a permissão já foi concedida (mantém
// o aparelho registrado mesmo após limpar dados/trocar chave). Best-effort.
export default function NotifBell() {
  const router = useRouter();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let alive = true;

    getNotifications().then((r) => {
      if (alive && r) setUnread(r.unread);
    });

    ensurePushSubscribed().catch(() => {});

    return () => {
      alive = false;
    };
  }, []);

  return (
    <button
      className="iconbtn"
      aria-label={unread > 0 ? `Notificações (${unread} não lidas)` : "Notificações"}
      onClick={() => router.push("/notificacoes")}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {unread > 0 && <span className="badge-count">{unread > 9 ? "9+" : unread}</span>}
    </button>
  );
}
