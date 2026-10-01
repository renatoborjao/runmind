// PDF do plano alimentar, gerado NO APP (jsPDF) — sem servidor, sem custo.
// Layout no molde de plano de nutricionista: cabeçalho com o dia-base em kcal,
// uma tabela por refeição (alimentos × porções × grupo × kcal), orientação,
// treinos longos, ajustes e orientações gerais. As libs só carregam ao clicar.

import type { NutritionPlan } from "./api";

const ACCENT: [number, number, number] = [40, 120, 90];
const INK: [number, number, number] = [30, 33, 40];
const MUTED: [number, number, number] = [110, 116, 128];
const MARGIN = 14;

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

// fontes padrão do PDF cobrem acentos latinos, mas não setas/emoji
function clean(t: string): string {
  return t.replace(/[→➜➔]/g, "->").replace(/[^\u0000-ÿ–—•]/g, "");
}

export async function downloadNutritionPlanPdf(plan: NutritionPlan, athleteName?: string | null): Promise<void> {
  const [{ jsPDF }, autoTableMod] = await Promise.all([import("jspdf"), import("jspdf-autotable")]);
  const autoTable = autoTableMod.default;

  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const tg = plan.targets;
  const menu = plan.menu;
  let y = 16;

  const ensure = (need: number) => {
    if (y + need > H - 18) {
      doc.addPage();
      y = 16;
    }
  };

  const heading = (text: string, size = 12) => {
    ensure(14);
    doc.setFont("helvetica", "bold").setFontSize(size).setTextColor(...ACCENT);
    doc.text(clean(text), MARGIN, y);
    y += size * 0.5 + 2;
  };

  const paragraph = (text: string, size = 9.5, color: [number, number, number] = INK) => {
    if (!text) return;
    doc.setFont("helvetica", "normal").setFontSize(size).setTextColor(...color);
    const lines = doc.splitTextToSize(clean(text), W - MARGIN * 2) as string[];
    ensure(lines.length * (size * 0.42) + 3);
    doc.text(lines, MARGIN, y);
    y += lines.length * (size * 0.42) + 3;
  };

  const table = (head: string[], body: string[][], widths?: number[]) => {
    autoTable(doc, {
      startY: y,
      head: [head],
      body,
      margin: { left: MARGIN, right: MARGIN },
      theme: "grid",
      styles: { font: "helvetica", fontSize: 9, cellPadding: 2, textColor: INK, lineColor: [215, 219, 226] },
      headStyles: { fillColor: ACCENT, textColor: 255, fontStyle: "bold" },
      alternateRowStyles: { fillColor: [247, 249, 248] },
      columnStyles: widths ? Object.fromEntries(widths.map((w, i) => [i, { cellWidth: w }])) : undefined,
    });
    y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 4;
  };

  // ---- cabeçalho ----
  doc.setFont("helvetica", "bold").setFontSize(18).setTextColor(...INK);
  doc.text("Plano alimentar", MARGIN, y);
  y += 7;
  doc.setFont("helvetica", "normal").setFontSize(10).setTextColor(...MUTED);
  doc.text(clean(`${athleteName ? athleteName + " · " : ""}gerado em ${fmtDate(plan.generated_on)} · Ritmind`), MARGIN, y);
  y += 8;

  heading(`Distribuição de porções diárias para ${tg.base.kcal} kcal`, 13);
  paragraph(
    `Objetivo: ${tg.goal_pt}${tg.target_weight_kg ? ` -> ${tg.target_weight_kg} kg` : ""}. ` +
      `Proteína ${tg.base.protein_g} g · Carboidrato ${tg.base.carb_g} g · Gordura ${tg.base.fat_g} g (dia-base: ${tg.base.label.toLowerCase()}).`,
  );
  table(
    ["Tipo de dia", "Dias", "Kcal", "Prot (g)", "Carb (g)"],
    tg.tiers.map((t) => [t.label, t.days_pt.join(", "), String(t.kcal), String(t.protein_g), String(t.carb_g)].map(clean)),
    [40, 64, 20, 24, 24],
  );

  // ---- refeições ----
  for (const m of menu.refeicoes) {
    ensure(30);
    heading(`${m.nome}${m.horario ? "  ·  " + m.horario : ""}`);
    m.opcoes.forEach((o, j) => {
      if (m.opcoes.length > 1 || o.titulo) paragraph(o.titulo || `Opção ${j + 1}`, 9, MUTED);
      table(
        ["Alimentos", "Porções", "Grupo alimentar", "Kcal"],
        o.linhas.map((r) => [clean(r.alimentos), clean(r.porcoes), clean(r.grupo), r.kcal ? String(r.kcal) : "-"]),
        [84, 18, 56, 18],
      );
      if (o.substituicao) paragraph(`Substituição: ${o.substituicao}`, 9, MUTED);
    });
    paragraph(m.orientacao);
    y += 1;
  }

  // ---- treinos longos ----
  heading("Treinos longos");
  paragraph(menu.durante_treino);
  table(
    ["Duração do treino", "Carboidrato durante", "Observação"],
    tg.fueling.map((f) => [f.faixa, f.carb_h, f.nota].map(clean)),
    [40, 40, 96],
  );
  paragraph(`Hidratação: ${tg.hydration}`, 9, MUTED);

  // ---- ajustes ----
  if (menu.ajustes.descanso || menu.ajustes.longao) {
    heading("Ajustes por tipo de dia");
    if (menu.ajustes.descanso) paragraph(`Dia de descanso: ${menu.ajustes.descanso}`);
    if (menu.ajustes.longao) paragraph(`Véspera e dia de longão: ${menu.ajustes.longao}`);
  }

  // ---- orientações ----
  if (menu.orientacoes.length) {
    heading("Orientações gerais");
    menu.orientacoes.forEach((t) => paragraph(`• ${t}`));
  }

  // ---- rodapé em todas as páginas ----
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(...MUTED);
    doc.text(
      clean("Plano gerado a partir da sua bioimpedância e do seu plano de treino; atualiza 1 vez por mês."),
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
