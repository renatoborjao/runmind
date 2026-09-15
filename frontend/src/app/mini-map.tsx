"use client";

import { useEffect, useRef } from "react";

// Mini-mapa estático (estilo Strava): tiles escuros do CARTO (grátis, com CORS)
// + a rota por cima, desenhados num canvas. Best-effort — sem tiles, mostra a
// rota sobre fundo escuro. Reaproveitável (home, feed social, etc.).

type Pt = { lat: number; lon: number };

function lon2x(lon: number, z: number) { return ((lon + 180) / 360) * 256 * Math.pow(2, z); }
function lat2y(lat: number, z: number) {
  const r = (lat * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 256 * Math.pow(2, z);
}
function tileURL(z: number, x: number, y: number) {
  const s = ["a", "b", "c"][(x + y) % 3];
  return `https://${s}.tile.openstreetmap.org/${z}/${x}/${y}.png`;
}
// sem crossOrigin: OSM não manda CORS, mas este canvas é só pra EXIBIR
// (nunca exporta/toBlob), então o "taint" não atrapalha.
function loadTile(url: string): Promise<HTMLImageElement | null> {
  return new Promise((res) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = () => res(null);
    img.src = url;
  });
}

async function draw(canvas: HTMLCanvasElement, points: Pt[]) {
  const W = canvas.width, H = canvas.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#E8E8EC";
  ctx.fillRect(0, 0, W, H);
  const good = points.filter((p) => p.lat && p.lon);
  if (good.length < 2) return;

  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const padLa = (maxLa - minLa) * 0.18 || 0.003, padLo = (maxLo - minLo) * 0.18 || 0.003;
  minLa -= padLa; maxLa += padLa; minLo -= padLo; maxLo += padLo;

  let z = 17;
  for (; z >= 3; z--) {
    if (lon2x(maxLo, z) - lon2x(minLo, z) <= W && lat2y(minLa, z) - lat2y(maxLa, z) <= H) break;
  }
  const originX = (lon2x(minLo, z) + lon2x(maxLo, z)) / 2 - W / 2;
  const originY = (lat2y(minLa, z) + lat2y(maxLa, z)) / 2 - H / 2;
  const maxT = Math.pow(2, z) - 1;

  const jobs: Promise<void>[] = [];
  for (let tx = Math.floor(originX / 256); tx <= Math.floor((originX + W) / 256); tx++) {
    for (let ty = Math.floor(originY / 256); ty <= Math.floor((originY + H) / 256); ty++) {
      if (ty < 0 || ty > maxT) continue;
      const gx = ((tx % (maxT + 1)) + (maxT + 1)) % (maxT + 1);
      const dx = tx * 256 - originX, dy = ty * 256 - originY;
      jobs.push(loadTile(tileURL(z, gx, ty)).then((img) => { if (img) ctx.drawImage(img, dx, dy, 256, 256); }));
    }
  }
  await Promise.all(jobs);

  const path = () => {
    ctx.beginPath();
    good.forEach((p, i) => { const x = lon2x(p.lon, z) - originX, y = lat2y(p.lat, z) - originY; if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  };
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  // casing branco pra rota destacar sobre o mapa claro
  ctx.strokeStyle = "#FFFFFF"; ctx.lineWidth = 9; path(); ctx.stroke();
  ctx.strokeStyle = "#0FB499"; ctx.lineWidth = 5; path(); ctx.stroke();

  const dot = (p: Pt, outer: string, inner: string) => {
    const x = lon2x(p.lon, z) - originX, y = lat2y(p.lat, z) - originY;
    ctx.fillStyle = outer; ctx.beginPath(); ctx.arc(x, y, 9, 0, 7); ctx.fill();
    ctx.fillStyle = inner; ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fill();
  };
  dot(good[0], "#FFFFFF", "#0FB499");
  dot(good[good.length - 1], "#FFFFFF", "#E24666");
}

export default function MiniMap({ points, height = 150 }: { points: Pt[]; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    cv.width = 720;
    cv.height = Math.round((height / 360) * 720);
    let alive = true;
    draw(cv, points).catch(() => {});
    return () => { alive = false; void alive; };
  }, [points, height]);
  return <canvas ref={ref} style={{ width: "100%", height, display: "block" }} aria-hidden />;
}
