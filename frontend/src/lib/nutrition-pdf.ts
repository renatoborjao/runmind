// PDF do plano alimentar, gerado NO APP (jsPDF) — sem servidor, sem custo.
// Layout no molde de plano de nutricionista: cabeçalho com o dia-base em kcal,
// uma tabela por refeição (alimentos × porções × grupo × kcal), orientação,
// treinos longos, ajustes e orientações gerais. As libs só carregam ao clicar.

import type { NutritionPlan } from "./api";

const ACCENT: [number, number, number] = [40, 120, 90];
const INK: [number, number, number] = [30, 33, 40];
const MUTED: [number, number, number] = [110, 116, 128];
const MARGIN = 14;

const AI_NOTE =
  "Os cálculos e o cardápio são gerados por inteligência artificial a partir da sua bioimpedância e do seu plano de treino. " +
  "São estimativas e não substituem um nutricionista: em caso de dúvida, condição de saúde ou necessidade específica, procure um profissional.";

// Marca no cabeçalho: ícone do app + "ritmind" (o wordmark oficial é branco com
// transparência, pintado aqui de grafite pro papel branco). Qualquer falha
// (imagem fora do ar, sem canvas) devolve null e o PDF sai igual, sem logo.
async function loadLogo(): Promise<{ icon: string; word: string; ratio: number } | null> {
  if (typeof document === "undefined") return null;
  try {
    const load = (src: string) =>
      new Promise<HTMLImageElement>((res, rej) => {
        const im = new Image();
        im.onload = () => res(im);
        im.onerror = () => rej(new Error(src));
        im.src = src;
      });
    const [icon, word] = await Promise.all([load("/icons/icon-192.png"), load("/brand/ritmind-wordmark.png")]);
    const toUrl = (im: HTMLImageElement, tint?: string) => {
      const w = im.naturalWidth;
      const h = im.naturalHeight;
      const layer = document.createElement("canvas");
      layer.width = w;
      layer.height = h;
      const lx = layer.getContext("2d");
      const out = document.createElement("canvas");
      out.width = w;
      out.height = h;
      const ox = out.getContext("2d");
      if (!lx || !ox) throw new Error("canvas");
      lx.drawImage(im, 0, 0);
      if (tint) {
        lx.globalCompositeOperation = "source-in";
        lx.fillStyle = tint;
        lx.fillRect(0, 0, w, h);
      }
      ox.fillStyle = "#ffffff";
      ox.fillRect(0, 0, w, h);
      ox.drawImage(layer, 0, 0);
      return out.toDataURL("image/jpeg", 0.92);
    };
    return { icon: toUrl(icon), word: toUrl(word, "#1E2128"), ratio: word.naturalWidth / word.naturalHeight };
  } catch {
    return null;
  }
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

// fontes padrão do PDF cobrem acentos latinos, mas não setas/emoji
function clean(t: string): string {
  return t.replace(/[→➜➔]/g, "->").replace(/[^\u0000-ÿ–—•]/g, "");
}

type Rgb = [number, number, number];
type Part =
  | { p: string; size?: number; color?: Rgb }
  | { t: { head: string[]; body: string[][]; widths?: number[] } };

export async function downloadNutritionPlanPdf(plan: NutritionPlan, athleteName?: string | null): Promise<void> {
  const [{ jsPDF }, autoTableMod] = await Promise.all([import("jspdf"), import("jspdf-autotable")]);
  const autoTable = autoTableMod.default;

  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const BOTTOM = H - 18;
  const TOP = 16;
  const tg = plan.targets;
  const menu = plan.menu;
  let y = TOP;

  const lastY = (d: unknown) => (d as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;

  const tableOpts = (t: { head: string[]; body: string[][]; widths?: number[] }) => ({
    head: [t.head],
    body: t.body,
    margin: { left: MARGIN, right: MARGIN },
    theme: "grid" as const,
    styles: { font: "helvetica", fontSize: 9, cellPadding: 2, textColor: INK, lineColor: [215, 219, 226] as Rgb },
    headStyles: { fillColor: ACCENT, textColor: 255, fontStyle: "bold" as const },
    alternateRowStyles: { fillColor: [247, 249, 248] as Rgb },
    columnStyles: t.widths ? Object.fromEntries(t.widths.map((w, i) => [i, { cellWidth: w }])) : undefined,
  });

  // ---- medição: altura exata de cada peça ANTES de desenhar ----
  const HEADING_H = 12;

  const paraLines = (text: string, size: number) => {
    doc.setFont("helvetica", "normal").setFontSize(size);
    return doc.splitTextToSize(clean(text), W - MARGIN * 2) as string[];
  };
  const paraHeight = (text: string, size = 9.5) => paraLines(text, size).length * (size * 0.42) + 3;

  const tableHeight = (t: { head: string[]; body: string[][]; widths?: number[] }) => {
    const scratch = new jsPDF({ unit: "mm", format: "a4" });
    autoTable(scratch, { ...tableOpts(t), startY: 0, margin: { left: MARGIN, right: MARGIN, top: 0, bottom: 0 } });
    return lastY(scratch) + 4;
  };

  const partHeight = (part: Part) => ("p" in part ? paraHeight(part.p, part.size) : tableHeight(part.t));

  const ensure = (need: number) => {
    if (y + need > BOTTOM) {
      doc.addPage();
      y = TOP;
    }
  };

  const drawPart = (part: Part) => {
    if ("p" in part) {
      const size = part.size ?? 9.5;
      const lines = paraLines(part.p, size);
      const h = lines.length * (size * 0.42) + 3;
      ensure(h);
      doc.setFont("helvetica", "normal").setFontSize(size).setTextColor(...(part.color ?? INK));
      doc.text(lines, MARGIN, y);
      y += h;
    } else {
      autoTable(doc, { ...tableOpts(part.t), startY: y, margin: { left: MARGIN, right: MARGIN, top: TOP, bottom: 18 } });
      y = lastY(doc) + 4;
    }
  };

  // Uma SEÇÃO: título + conteúdo. O título nunca fica sozinho no fim da folha:
  // reserva a altura do título + das primeiras `keep` peças (todas, por padrão);
  // se não cabe, a seção inteira começa na página seguinte.
  const section = (title: string, parts: Part[], opts: { size?: number; keep?: number } = {}) => {
    const size = opts.size ?? 12;
    const keep = opts.keep ?? parts.length;
    const need = HEADING_H + parts.slice(0, keep).reduce((sum, part) => sum + partHeight(part), 0);
    ensure(Math.min(need, BOTTOM - TOP));
    doc.setFont("helvetica", "bold").setFontSize(size).setTextColor(...ACCENT);
    doc.text(clean(title), MARGIN, y);
    y += size * 0.42 + 1.5;
    parts.forEach(drawPart);
    y += 2;
  };

  // ---- cabeçalho ----
  const logo = await loadLogo();
  if (logo) {
    doc.addImage(logo.icon, "JPEG", MARGIN, y, 10, 10);
    const wh = 6.5;
    doc.addImage(logo.word, "JPEG", MARGIN + 12.5, y + 1.75, wh * logo.ratio, wh);
    y += 21;
  }
  doc.setFont("helvetica", "bold").setFontSize(18).setTextColor(...INK);
  doc.text("Plano alimentar", MARGIN, y);
  y += 7;
  doc.setFont("helvetica", "normal").setFontSize(10).setTextColor(...MUTED);
  doc.text(clean(`${athleteName ? athleteName + " · " : ""}gerado em ${fmtDate(plan.generated_on)} · Ritmind`), MARGIN, y);
  y += 6;
  drawPart({ p: AI_NOTE, size: 8.5, color: MUTED });
  y += 2;

  section(
    `Distribuição de porções diárias para ${tg.base.kcal} kcal`,
    [
      {
        p:
          `Objetivo: ${tg.goal_pt}${tg.target_weight_kg ? ` -> ${tg.target_weight_kg} kg` : ""}. ` +
          `Proteína ${tg.base.protein_g} g · Carboidrato ${tg.base.carb_g} g · Gordura ${tg.base.fat_g} g (dia-base: ${tg.base.label.toLowerCase()}).`,
      },
      {
        t: {
          head: ["Tipo de dia", "Dias", "Kcal", "Prot (g)", "Carb (g)"],
          body: tg.tiers.map((t) => [t.label, t.days_pt.join(", "), String(t.kcal), String(t.protein_g), String(t.carb_g)].map(clean)),
          widths: [40, 64, 20, 24, 24],
        },
      },
    ],
    { size: 13 },
  );

  // ---- refeições: cada uma inteira na mesma folha ----
  for (const m of menu.refeicoes) {
    const parts: Part[] = [];
    m.opcoes.forEach((o, j) => {
      if (m.opcoes.length > 1 || o.titulo) parts.push({ p: o.titulo || `Opção ${j + 1}`, size: 9, color: MUTED });
      parts.push({
        t: {
          head: ["Alimentos", "Porções", "Grupo alimentar", "Kcal"],
          body: o.linhas.map((r) => [clean(r.alimentos), clean(r.porcoes), clean(r.grupo), r.kcal ? String(r.kcal) : "-"]),
          widths: [84, 18, 56, 18],
        },
      });
      if (o.substituicao) parts.push({ p: `Substituição: ${o.substituicao}`, size: 9, color: MUTED });
    });
    if (m.orientacao) parts.push({ p: m.orientacao });
    section(`${m.nome}${m.horario ? "  ·  " + m.horario : ""}`, parts);
  }

  // ---- treinos longos: título, conduta e tabela sempre juntos ----
  const longParts: Part[] = [];
  if (menu.durante_treino) longParts.push({ p: menu.durante_treino });
  longParts.push({
    t: {
      head: ["Duração do treino", "Carboidrato durante", "Observação"],
      body: tg.fueling.map((f) => [f.faixa, f.carb_h, f.nota].map(clean)),
      widths: [40, 40, 96],
    },
  });
  longParts.push({ p: `Hidratação: ${tg.hydration}`, size: 9, color: MUTED });
  section("Treinos longos", longParts);

  // ---- ajustes ----
  if (menu.ajustes.descanso || menu.ajustes.longao) {
    const parts: Part[] = [];
    if (menu.ajustes.descanso) parts.push({ p: `Dia de descanso: ${menu.ajustes.descanso}` });
    if (menu.ajustes.longao) parts.push({ p: `Véspera e dia de longão: ${menu.ajustes.longao}` });
    section("Ajustes por tipo de dia", parts);
  }

  // ---- orientações: o título acompanha pelo menos as 2 primeiras ----
  if (menu.orientacoes.length) {
    section("Orientações gerais", menu.orientacoes.map((t) => ({ p: `• ${t}` })), { keep: 2 });
  }

  // ---- rodapé em todas as páginas ----
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(...MUTED);
    doc.text(
      clean("Estimativa gerada por IA, não substitui um nutricionista. Atualiza 1 vez por mês."),
      MARGIN,
      H - 8,
    );
    doc.text(`${i}/${pages}`, W - MARGIN, H - 8, { align: "right" });
  }

  await deliver(doc.output("blob"), `plano-alimentar-${plan.generated_on}.pdf`);
}

// Entrega o arquivo SEM tirar o atleta da tela: no celular abre a folha de
// compartilhar (salvar em Arquivos, WhatsApp, e-mail); no desktop, baixa. O
// doc.save() do jsPDF em PWA instalado pode navegar a janela pro blob.
async function deliver(blob: Blob, name: string): Promise<void> {
  const file = new File([blob], name, { type: "application/pdf" });
  const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
  const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

  if (touch && nav.canShare?.({ files: [file] }) && nav.share) {
    try {
      await nav.share({ files: [file], title: "Plano alimentar" });
      return;
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return; // o atleta fechou a folha
      // qualquer outra falha cai no download normal
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
