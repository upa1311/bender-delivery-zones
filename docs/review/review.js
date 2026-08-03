/* /review/ — DESIGN tariff model + zones. Not an approved public price.
 * base = 14 (<=3km) else 14+(km-3)*4; external_surcharge = max(5, external_km*2)
 * ONLY past the Парканы tariff boundary; reference = base + surcharge. */
"use strict";

const OSM_ATTR = "© OpenStreetMap contributors";
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
const basePrice = (km) => (km <= 3 ? 14 : 14 + (km - 3) * 4);
const externalSurcharge = (km) => (km <= 0 ? 0 : Math.max(5, km * 2));

const ZCOL = { 1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828", 5: "#8338ec", 6: "#0e7490" };
const SCOL = { 2: "#9ca3af", 4: "#92400e", 5: "#111827", 6: "#ec4899" }; // non-routed by status code
const STATUS_RU = { routed: "маршрут построен", duplicate: "дубликат",
  invalid_address: "нет координат/адреса", outside_supported_area: "вне зоны обслуживания",
  unreachable: "маршрут не построен", manual_review: "ручная проверка" };
const SCODE = { routed: 1, duplicate: 2, outside_supported_area: 4, unreachable: 5, manual_review: 6 };
const LSKEY = "bdz_tariff_boundary_v1";

async function loadJSON(p) { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); }

let MAP, POINTS = [], POINT_LAYER, ROUTE, CUM, TOTAL, boundary, bIdx, approved = null;

function priceCards(total, boundaryKm) {
  const ext = Math.max(0, total - boundaryKm), base = basePrice(total), sur = externalSurcharge(ext);
  const card = (l, v) => `<div class="price-card"><div class="lbl">${l}</div><div class="val">${v}</div></div>`;
  document.getElementById("price-grid").innerHTML =
    card("маршрут км", total.toFixed(3)) + card("до границы", boundaryKm.toFixed(3))
    + card("внешние км", ext.toFixed(3)) + card("итог ₽", (base + sur).toFixed(2));
  return { ext, base, sur, ref: base + sur };
}

function drawPoints() {
  if (POINT_LAYER) MAP.removeLayer(POINT_LAYER);
  const mode = document.querySelector('input[name=mode]:checked').value;
  const show = {}; document.querySelectorAll("#status-filter input").forEach((c) => { show[c.value] = c.checked; });
  const markers = [];
  for (const p of POINTS) {
    const [lon, lat, nz, sc, price, oldk4] = p;
    if (!show[String(sc)]) continue;
    let col;
    if (mode === "old") col = oldk4 > 0 ? ZCOL[oldk4] : "#cbd5e1";
    else col = sc === 1 ? (ZCOL[nz] || "#999") : (SCOL[sc] || "#999");
    markers.push(L.circleMarker([lat, lon], { radius: 2.2, weight: 0, fillColor: col,
      fillOpacity: sc === 1 ? 0.85 : 0.55 }));
  }
  POINT_LAYER = L.layerGroup(markers).addTo(MAP);
}

function renderStatus(sum) {
  const sc = sum.status_counts, order = ["routed", "duplicate", "invalid_address",
    "outside_supported_area", "unreachable", "manual_review"];
  let rows = "";
  order.forEach((k) => { if (sc[k] != null) rows += `<div>${STATUS_RU[k]}: <b>${sc[k]}</b></div>`; });
  const ok = sum.status_sum === 9216;
  document.getElementById("status-summary").innerHTML = rows
    + `<div style="margin-top:4px" class="${ok ? "ok" : "warn"}">Σ = ${sum.status_sum} `
    + `${ok ? "= 9 216 ✓" : "≠ 9 216 ✗"}</div>`;
  // status filter checkboxes (invalid has no coords -> not on map)
  document.getElementById("status-filter").innerHTML = order
    .filter((k) => k !== "invalid_address")
    .map((k) => `<label class="flt"><input type="checkbox" value="${SCODE[k]}" checked> ${STATUS_RU[k]}</label>`).join("");
}

function renderZones(sum) {
  const z = sum.zone_stats;
  let rows = Object.keys(z).sort((a, b) => a - b).map((zid) => {
    const s = z[zid];
    return `<div><span class="zsw" style="background:${ZCOL[zid]}"></span>Зона ${zid}: `
      + `<b>${s.pmin}–${s.pmax} ₽</b>, ${s.kmin}–${s.kmax} км, ${s.n} адр., внешних ${s.external}`
      + `<br><span class="muted" style="font-size:11px">${(s.examples || []).map(esc).join(", ")}</span></div>`;
  }).join("");
  document.getElementById("zone-legend").innerHTML =
    `<div class="small" style="margin-bottom:4px">Рекомендовано <b>${sum.recommended_zone_count}</b> зон `
    + `(естественные границы по цене, не квартили). Границы ₽: ${sum.recommended_breaks_price.join(", ")}.</div>` + rows;
}

/* ---- persistent tariff boundary ---- */
function saveBoundary(obj) { try { localStorage.setItem(LSKEY, JSON.stringify(obj)); } catch (e) { /* */ } }
function loadBoundary() { try { return JSON.parse(localStorage.getItem(LSKEY)); } catch (e) { return null; } }
function nowISO() { return new Date().toISOString(); }

function updateBoundaryUI() {
  const bkm = CUM[bIdx], ll = ROUTE[bIdx], r = priceCards(TOTAL, bkm);
  document.getElementById("bcoords").innerHTML =
    `Граница: <code>${ll[1].toFixed(6)}, ${ll[0].toFixed(6)}</code> · ${bkm.toFixed(3)} км от старта · `
    + `внешних ${r.ext.toFixed(3)} км` + (approved
      ? `<br><span class="ok">Утверждено: ${esc(approved.approved_at)}</span>` : " · <span class='warn'>PROVISIONAL</span>");
}

async function init() {
  MAP = L.map("rmap", { preferCanvas: true, zoomControl: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTR }).addTo(MAP);

  let sum, pts, route, addrIdx;
  try {
    [sum, pts, route, addrIdx] = await Promise.all([
      loadJSON("data/reference-tariff-v3-summary.json"),
      loadJSON("data/zone-points.json"),
      loadJSON("data/parkany-route-boundary.json"),
      loadJSON("data/address-index.json"),
    ]);
  } catch (e) {
    document.getElementById("rmap").innerHTML = "Ошибка загрузки данных: " + esc(e.message); return;
  }
  POINTS = pts.points;
  renderStatus(sum); renderZones(sum);

  // map extent from points
  const lats = POINTS.map((p) => p[1]), lons = POINTS.map((p) => p[0]);
  MAP.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { padding: [20, 20] });
  drawPoints();
  document.querySelectorAll('input[name=mode]').forEach((r) => r.addEventListener("change", drawPoints));
  document.getElementById("status-filter").addEventListener("change", drawPoints);

  // origin
  L.circleMarker([sum.origin.lat, sum.origin.lon], { radius: 7, color: "#111827",
    fillColor: "#111827", fillOpacity: 1, weight: 2 }).addTo(MAP).bindPopup("Точка отправления (фиксированная)");

  // Парканы route + draggable boundary
  const coords = route.route_lonlat; CUM = route.route_cum_km; TOTAL = route.osrm_total_km;
  ROUTE = coords;
  L.polyline(coords.map((c) => [c[1], c[0]]), { color: "#1f4e79", weight: 4, opacity: 0.9 }).addTo(MAP);
  L.circleMarker([route.destination.lat, route.destination.lon], { radius: 6, color: "#111827",
    fillColor: "#2563eb", fillOpacity: 1, weight: 2 }).addTo(MAP).bindPopup(esc(route.destination.address));

  const saved = loadBoundary();
  bIdx = CUM.findIndex((v) => v >= route.provisional_boundary_km_from_origin);
  if (bIdx < 0) bIdx = Math.floor(coords.length / 2);
  if (saved && typeof saved.boundary_km === "number") {
    const j = CUM.findIndex((v) => v >= saved.boundary_km); if (j >= 0) bIdx = j;
    if (saved.status === "owner_approved") approved = saved;
  }
  boundary = L.marker([coords[bIdx][1], coords[bIdx][0]], { draggable: true,
    icon: L.divIcon({ className: "", iconSize: [18, 18], html:
      '<div style="width:16px;height:16px;border-radius:50%;background:#dc2626;border:3px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5)"></div>' }),
  }).addTo(MAP).bindTooltip("Тарифная граница (PROVISIONAL) — тяните");
  const nearest = (lat, lng) => { let b = 0, bd = Infinity;
    for (let i = 0; i < coords.length; i++) { const d = (coords[i][1] - lat) ** 2 + (coords[i][0] - lng) ** 2; if (d < bd) { bd = d; b = i; } } return b; };
  boundary.on("drag", (e) => { const p = e.target.getLatLng(); bIdx = nearest(p.lat, p.lng);
    boundary.setLatLng([coords[bIdx][1], coords[bIdx][0]]); approved = null; updateBoundaryUI(); });
  updateBoundaryUI();

  const boundaryObj = (status) => ({ checkpoint: { lat: +coords[bIdx][1].toFixed(6),
    lon: +coords[bIdx][0].toFixed(6), status, approved_at: nowISO() }, boundary_km: CUM[bIdx],
    external_km: Math.max(0, TOTAL - CUM[bIdx]), note: "DESIGN provisional; not final until owner-approved" });
  document.getElementById("approve").addEventListener("click", () => {
    approved = { approved_at: nowISO(), boundary_km: CUM[bIdx], status: "owner_approved",
      lat: +coords[bIdx][1].toFixed(6), lon: +coords[bIdx][0].toFixed(6) };
    saveBoundary(approved); updateBoundaryUI();
    document.getElementById("approve-out").innerHTML = `<span class="ok">Сохранено (переживёт перезагрузку): `
      + `${approved.lat}, ${approved.lon} @ ${esc(approved.approved_at)}</span>`;
  });
  document.getElementById("copy").addEventListener("click", () => {
    const t = `${coords[bIdx][1].toFixed(6)}, ${coords[bIdx][0].toFixed(6)}`;
    navigator.clipboard && navigator.clipboard.writeText(t);
    document.getElementById("approve-out").textContent = "Скопировано: " + t;
  });
  document.getElementById("download").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(boundaryObj(approved ? "owner_approved" : "provisional"), null, 2)],
      { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "tariff-boundary.json"; a.click();
  });
  document.getElementById("reset").addEventListener("click", () => {
    try { localStorage.removeItem(LSKEY); } catch (e) { /* */ }
    approved = null; bIdx = CUM.findIndex((v) => v >= route.provisional_boundary_km_from_origin);
    if (bIdx < 0) bIdx = Math.floor(coords.length / 2);
    boundary.setLatLng([coords[bIdx][1], coords[bIdx][0]]); updateBoundaryUI();
    document.getElementById("approve-out").textContent = "Сброшено к provisional.";
  });

  // Парканы block
  const r0 = priceCards(TOTAL, CUM[bIdx]);
  document.getElementById("parkany-block").innerHTML =
    `Отправление → ${esc(route.destination.address)}: OSRM <b>${TOTAL} км</b>, контроль Яндекс `
    + `<b>${route.yandex_control_km} км</b> (совпадает). При provisional-границе на `
    + `${CUM[bIdx].toFixed(3)} км внешних <b>${r0.ext.toFixed(3)} км</b>, надбавка `
    + `<b>${r0.sur.toFixed(2)} ₽</b>, итог <b>${r0.ref.toFixed(2)} ₽</b>. Внешняя надбавка `
    + "применяется ТОЛЬКО после границы.";

  // Кишинёвская block
  const kd = sum.kishinevskaya, fixed = sum.kishinevskaya_fixed_count;
  let krows = kd.map((k) => `<tr><td>${esc(k.address)}</td><td class="num">${k.old_km}</td>`
    + `<td class="num">${k.new_km}</td><td>${esc(k.status)}</td>`
    + `<td>${k.reason.includes("shortest") ? "исправлено (кратчайший маршрут)" : "без изменений"}</td></tr>`).join("");
  document.getElementById("kish-block").innerHTML =
    `<p>Исправлено записей: <b>${fixed} из ${kd.length}</b> (выбран кратчайший по расстоянию маршрут вместо `
    + "быстрейшего по времени объезда). Разные участки улицы дают разные реальные расстояния — не подгонялись.</p>"
    + `<table class="rt"><thead><tr><th>адрес</th><th>старое км</th><th>новое км</th><th>статус</th><th>причина</th></tr></thead>`
    + `<tbody>${krows}</tbody></table>`;

  // address search
  const idx = addrIdx.addresses;
  const inp = document.getElementById("addr-search"), out = document.getElementById("addr-results");
  let hl = null;
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase(); if (q.length < 2) { out.textContent = ""; return; }
    const m = idx.filter((a) => a[0].toLowerCase().includes(q)).slice(0, 8);
    out.innerHTML = m.map((a, i) => `<div style="cursor:pointer;padding:2px 0" data-i="${i}">`
      + `<b>${esc(a[0])}</b> — ${a[4] != null ? a[4] + " ₽, зона " + a[3] : esc(STATUS_RU[a[5]] || a[5])}</div>`).join("") || "не найдено";
    out.querySelectorAll("[data-i]").forEach((el) => el.addEventListener("click", () => {
      const a = m[+el.dataset.i]; if (hl) MAP.removeLayer(hl);
      hl = L.circleMarker([a[2], a[1]], { radius: 8, color: "#111", weight: 3, fillColor: "#fff", fillOpacity: 1 })
        .addTo(MAP).bindPopup(`<b>${esc(a[0])}</b><br>${a[4] != null ? "итог " + a[4] + " ₽, зона " + a[3] : esc(STATUS_RU[a[5]])}`).openPopup();
      MAP.setView([a[2], a[1]], 16);
    }));
  });
}

init();
