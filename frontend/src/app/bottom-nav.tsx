"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

function Icon({ name }: { name: string }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (name === "inicio")
    return (<svg {...common}><path d="M3 11l9-8 9 8" /><path d="M5 10v10h14V10" /></svg>);
  if (name === "treino")
    return (<svg {...common}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M8 2v4M16 2v4M3 10h18" /></svg>);
  if (name === "evolucao")
    return (<svg {...common}><path d="M3 3v18h18" /><path d="M7 14l4-4 3 3 5-6" /></svg>);
  return (<svg {...common}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>);
}

export default function BottomNav() {
  const path = usePathname();
  const on = (p: string) => (path === p || path === p + "/" ? "on" : "");

  return (
    <nav className="bottomnav">
      <Link href="/inicio" className={on("/inicio")}><Icon name="inicio" />Início</Link>
      <Link href="/treino" className={on("/treino")}><Icon name="treino" />Treino</Link>
      <Link href="/evolucao" className={on("/evolucao")}><Icon name="evolucao" />Evolução</Link>
      <Link href="/coach" className={on("/coach")}><Icon name="coach" />Coach</Link>
    </nav>
  );
}
