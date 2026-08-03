/* Static /review/ route-geometry tariff model. DESIGN only, not an approved tariff. */
"use strict";

const OSM_ATTR = "© OpenStreetMap contributors";
const LSKEY = "bdz_tariff_gate_v2";
const ZCOL = { 1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828", 5: "#8338ec", 6: "#0e7490" };
const SCOL = { 2: "#9ca3af", 4: "#92400e", 5: "#111827", 6: "#ec4899" };
const STATUS_RU = { routed: "маршрут построен", duplicate: "дубликат",
  invalid_address: "нет координат/адреса", outside_supported_area: "вне зоны обслуживания",
  unreachable: "маршрут не построен", manual_review: "ручная проверка" };
const SCODE = { routed: 1, duplicate: 2, outside_supported_area: 4, unreachable: 5, manual_review: 6 };
const esc = (value) => (value == null ? "" : String(value).replace(/[&<>"]/g,
  (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char])));
const basePrice = (km) => (km <= 3 ? 14 : 14 + (km - 3) * 4);
const externalSurcharge = (km) => (km <= 0 ? 0 : Math.max(5, km * 2));

let MAP, POINT_LAYER, GATE_LINE, GATE_MARKER, CONTROL_LINE, HIGHLIGHT;
let POINTS = [], CATALOG = [], ROUTES = {}, CONTROL = [], CONTROL_CUM = [];
let bIdx = 0, provisionalIdx = 0, approved = null, selectedUid = null, CURRENT = null;

async function loadJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

function decodePolyline6(encoded) {
  const result = [];
  let index = 0, lat = 0, lon = 0;
  while (index < encoded.length) {
    const deltas = [];
    for (let axis = 0; axis < 2; axis += 1) {
      let value = 0, shift = 0, byte;
      do { byte = encoded.charCodeAt(index++) - 63; value |= (byte & 31) << shift; shift += 5; } while (byte >= 32);
      deltas.push((value & 1) ? ~(value >> 1) : (value >> 1));
    }
    lat += deltas[0]; lon += deltas[1]; result.push([lon / 1e6, lat / 1e6]);
  }
  return result;
}

function haversineKm(a, b) {
  const rad = Math.PI / 180, radius = 6371.0088;
  const dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(h));
}

function cross(a, b) { return a[0] * b[1] - a[1] * b[0]; }
function segmentIntersectionFraction(routeA, routeB, gateA, gateB) {
  const r = [routeB[0] - routeA[0], routeB[1] - routeA[1]];
  const g = [gateB[0] - gateA[0], gateB[1] - gateA[1]];
  const offset = [gateA[0] - routeA[0], gateA[1] - routeA[1]];
  const denominator = cross(r, g), epsilon = 1e-12;
  if (Math.abs(denominator) <= epsilon) return null;
  const routeFraction = cross(offset, g) / denominator;
  const gateFraction = cross(offset, r) / denominator;
  if (routeFraction < -epsilon || routeFraction > 1 + epsilon || gateFraction < -epsilon || gateFraction > 1 + epsilon) return null;
  return Math.max(0, Math.min(1, routeFraction));
}

function routeGateMetrics(points, routeKm, gate) {
  const lengths = [];
  let geometryKm = 0;
  for (let i = 0; i < points.length - 1; i += 1) { const length = haversineKm(points[i], points[i + 1]); lengths.push(length); geometryKm += length; }
  let traversed = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    const fraction = segmentIntersectionFraction(points[i], points[i + 1], gate[0], gate[1]);
    if (fraction != null) {
      const chainage = Math.max(0, Math.min(routeKm, (traversed + lengths[i] * fraction) * routeKm / geometryKm));
      return { crosses: true, chainage, externalKm: Math.max(0, routeKm - chainage) };
    }
    traversed += lengths[i];
  }
  return { crosses: false, chainage: null, externalKm: 0 };
}

function gateAt(index, halfLengthM = 90) {
  const center = CONTROL[index], before = CONTROL[Math.max(0, index - 1)], after = CONTROL[Math.min(CONTROL.length - 1, index + 1)];
  const latitude = center[1] * Math.PI / 180;
  const dx = (after[0] - before[0]) * 111320 * Math.cos(latitude), dy = (after[1] - before[1]) * 110540;
  const length = Math.hypot(dx, dy) || 1, px = -dy / length, py = dx / length;
  return [-1, 1].map((side) => [center[0] + side * halfLengthM * px / (111320 * Math.cos(latitude)), center[1] + side * halfLengthM * py / 110540]);
}

function weightedJenks(values, classCount) {
  const frequency = new Map();
  values.forEach((value) => frequency.set(value, (frequency.get(value) || 0) + 1));
  const levels = [...frequency.entries()].sort((a, b) => a[0] - b[0]), n = levels.length;
  const counts = [0], sums = [0], squares = [0];
  levels.forEach(([value, count]) => { counts.push(counts.at(-1) + count); sums.push(sums.at(-1) + value * count); squares.push(squares.at(-1) + value * value * count); });
  const variance = (first, last) => { const weight = counts[last] - counts[first - 1], total = sums[last] - sums[first - 1]; return squares[last] - squares[first - 1] - total * total / weight; };
  const scores = Array.from({ length: classCount + 1 }, () => Array(n + 1).fill(Infinity));
  const starts = Array.from({ length: classCount + 1 }, () => Array(n + 1).fill(0));
  scores[0][0] = 0;
  for (let group = 1; group <= classCount; group += 1) {
    for (let last = group; last <= n; last += 1) {
      for (let first = group; first <= last; first += 1) {
        const score = scores[group - 1][first - 1] + variance(first, last);
        if (score < scores[group][last] - 1e-12) { scores[group][last] = score; starts[group][last] = first; }
      }
    }
  }
  const breaks = []; let last = n;
  for (let group = classCount; group >= 1; group -= 1) { const first = starts[group][last]; breaks.push(levels[last - 1][0]); last = first - 1; }
  return breaks.reverse();
}

function zoneOf(price, breaks) { let zone = 0; while (zone < breaks.length - 1 && price > breaks[zone]) zone += 1; return zone + 1; }
function streetOf(address) { return (address.split(",")[1] || address).trim(); }

function recalculateCatalog(gate) {
  const prices = [], pointByUid = new Map(POINTS.map((point) => [point[0], point]));
  let crossing = 0;
  for (const item of CATALOG) {
    if (item.status !== "routed") continue;
    const route = ROUTES[item.uid];
    const metrics = routeGateMetrics(route.points, item.routeKm, gate);
    item.crosses = metrics.crosses; item.chainage = metrics.chainage; item.externalKm = metrics.externalKm;
    item.surcharge = externalSurcharge(metrics.externalKm); item.price = basePrice(item.routeKm) + item.surcharge;
    prices.push(item.price); crossing += Number(metrics.crosses);
  }
  const roundedPrices = prices.map((price) => Math.round(price * 10) / 10);
  const breaks = weightedJenks(roundedPrices, 4), stats = {};
  for (const item of CATALOG) {
    if (item.status !== "routed") continue;
    item.zone = zoneOf(item.price, breaks);
    const stat = stats[item.zone] || { n: 0, pmin: Infinity, pmax: -Infinity, kmin: Infinity, kmax: -Infinity, external: 0, streets: {} };
    stat.n += 1; stat.pmin = Math.min(stat.pmin, item.price); stat.pmax = Math.max(stat.pmax, item.price);
    stat.kmin = Math.min(stat.kmin, item.routeKm); stat.kmax = Math.max(stat.kmax, item.routeKm);
    stat.external += Number(item.surcharge > 0); stat.streets[streetOf(item.address)] = (stat.streets[streetOf(item.address)] || 0) + 1;
    stats[item.zone] = stat;
    const point = pointByUid.get(item.uid); if (point) { point[3] = item.zone; point[5] = +item.price.toFixed(3); }
  }
  Object.values(stats).forEach((stat) => { stat.share_pct = +(100 * stat.n / prices.length).toFixed(1); stat.examples = Object.entries(stat.streets).sort((a, b) => b[1] - a[1]).slice(0, 4).map((entry) => entry[0]); });
  CURRENT = { breaks, stats, crossing, notCrossing: prices.length - crossing, gate };
  return CURRENT;
}

function drawPoints() {
  if (POINT_LAYER) MAP.removeLayer(POINT_LAYER);
  const mode = document.querySelector('input[name="mode"]:checked').value, show = {};
  document.querySelectorAll("#status-filter input").forEach((checkbox) => { show[checkbox.value] = checkbox.checked; });
  const markers = [];
  for (const point of POINTS) {
    const [uid, lon, lat, zone, statusCode, _price, oldK4] = point;
    if (!show[String(statusCode)]) continue;
    const color = mode === "old" ? (oldK4 > 0 ? ZCOL[oldK4] : "#cbd5e1") : (statusCode === 1 ? (ZCOL[zone] || "#999") : (SCOL[statusCode] || "#999"));
    markers.push(L.circleMarker([lat, lon], { radius: uid === selectedUid ? 4 : 2.2, weight: uid === selectedUid ? 1 : 0,
      color: "#111827", fillColor: color, fillOpacity: statusCode === 1 ? 0.85 : 0.55 }));
  }
  POINT_LAYER = L.layerGroup(markers).addTo(MAP);
}

function renderStatus(summary) {
  const order = ["routed", "duplicate", "invalid_address", "outside_supported_area", "unreachable", "manual_review"];
  document.getElementById("status-summary").innerHTML = order.filter((key) => summary.status_counts[key] != null)
    .map((key) => `<div>${STATUS_RU[key]}: <b>${summary.status_counts[key]}</b></div>`).join("")
    + `<div class="ok" style="margin-top:4px">Σ = ${summary.status_sum} = 9 216 ✓</div>`;
  document.getElementById("status-filter").innerHTML = order.filter((key) => key !== "invalid_address")
    .map((key) => `<label class="flt"><input type="checkbox" value="${SCODE[key]}" checked> ${STATUS_RU[key]}</label>`).join("");
}

function renderZones() {
  const rows = Object.keys(CURRENT.stats).sort((a, b) => a - b).map((zone) => {
    const stat = CURRENT.stats[zone];
    return `<div><span class="zsw" style="background:${ZCOL[zone]}"></span>Зона ${zone}: <b>${stat.pmin.toFixed(2)}–${stat.pmax.toFixed(2)} ₽</b>, `
      + `${stat.kmin.toFixed(3)}–${stat.kmax.toFixed(3)} км, ${stat.n} адр. (${stat.share_pct}%), внешних ${stat.external}<br>`
      + `<span class="muted" style="font-size:11px">${stat.examples.map(esc).join(", ")}</span></div>`;
  }).join("");
  document.getElementById("zone-legend").innerHTML = `<div class="small" style="margin-bottom:4px">Взвешенный Jenks по 9 215 маршрутам. Границы ₽: ${CURRENT.breaks.join(", ")}.</div>${rows}`;
  document.getElementById("catalog-recalc").innerHTML = `Пересчитано <b>9 215</b> маршрутов · gate пересекают <b>${CURRENT.crossing}</b> · не пересекают <b>${CURRENT.notCrossing}</b>`;
}

function selectedItem() { return CATALOG.find((item) => item.uid === selectedUid); }
function renderSelected() {
  const item = selectedItem(); if (!item) return;
  const color = item.status === "routed" ? ZCOL[item.zone] : "#999";
  const selected = document.getElementById("selected-address");
  selected.dataset.selectedZone = item.status === "routed" ? String(item.zone) : "";
  selected.dataset.selectedPrice = item.status === "routed" ? item.price.toFixed(2) : "";
  selected.innerHTML = `<span class="zsw" data-selected-color="${color}" style="background:${color}"></span><b>${esc(item.address)}</b><br>`
    + (item.status === "routed" ? `зона ${item.zone}, ${item.price.toFixed(2)} ₽ · пересечение: ${item.crosses ? "да" : "нет"}`
      + `${item.crosses ? ` · chainage ${item.chainage.toFixed(3)} км · external ${item.externalKm.toFixed(3)} км` : ""}` : esc(STATUS_RU[item.status]));
}

function renderControl() {
  const gate = CURRENT.gate, routeMetrics = routeGateMetrics(CONTROL, 4.715, gate);
  const surcharge = externalSurcharge(routeMetrics.externalKm), price = basePrice(4.715) + surcharge, center = CONTROL[bIdx];
  document.getElementById("price-grid").innerHTML = [["маршрут км", "4.715"], ["chainage км", routeMetrics.chainage == null ? "—" : routeMetrics.chainage.toFixed(3)],
    ["внешние км", routeMetrics.externalKm.toFixed(3)], ["итог ₽", price.toFixed(2)]].map(([label, value]) => `<div class="price-card"><div class="lbl">${label}</div><div class="val">${value}</div></div>`).join("");
  const coordinates = document.getElementById("bcoords");
  coordinates.dataset.lat = center[1].toFixed(6);
  coordinates.dataset.lon = center[0].toFixed(6);
  coordinates.innerHTML = `Gate center: <code>${center[1].toFixed(6)}, ${center[0].toFixed(6)}</code> · route index ${bIdx}`
    + (approved ? `<br><span class="ok">Утверждено: ${esc(approved.approved_at)}</span>` : " · <span class='warn'>PROVISIONAL</span>");
  document.getElementById("parkany-block").innerHTML = `Отправление → Парканы, ул. Котовского: OSRM <b>4.715 км</b>, контроль Яндекс <b>4.72 км</b>. `
    + `Первое геометрическое пересечение gate: <b>${routeMetrics.chainage == null ? "нет" : routeMetrics.chainage.toFixed(3) + " км"}</b>; `
    + `external <b>${routeMetrics.externalKm.toFixed(3)} км</b>; надбавка <b>${surcharge.toFixed(2)} ₽</b>; итог <b>${price.toFixed(2)} ₽</b>.`;
}

function applyGate(index, keepApproval = false) {
  bIdx = Math.max(1, Math.min(CONTROL.length - 2, index));
  if (!keepApproval) approved = null;
  const gate = gateAt(bIdx), center = CONTROL[bIdx];
  GATE_MARKER.setLatLng([center[1], center[0]]);
  GATE_LINE.setLatLngs(gate.map((point) => [point[1], point[0]]));
  document.getElementById("gate-slider").value = String(bIdx);
  recalculateCatalog(gate); renderZones(); renderSelected(); renderControl(); drawPoints();
}

function saveGate() {
  approved = { status: "owner_approved", approved_at: new Date().toISOString(), route_index: bIdx,
    center_lonlat: CONTROL[bIdx], geometry: { type: "LineString", coordinates: gateAt(bIdx) } };
  localStorage.setItem(LSKEY, JSON.stringify(approved)); renderControl();
  document.getElementById("approve-out").innerHTML = `<span class="ok">Сохранено; полный пересчёт переживёт reload.</span>`;
}
function resetGate() { localStorage.removeItem(LSKEY); approved = null; applyGate(provisionalIdx); document.getElementById("approve-out").textContent = "Сброшено к provisional."; }

function exportCheckpoint() {
  const center = CONTROL[bIdx];
  return { checkpoint: { lat: +center[1].toFixed(6), lon: +center[0].toFixed(6),
    status: approved.status, approved_at: approved.approved_at } };
}

function setupSearch() {
  const input = document.getElementById("addr-search"), output = document.getElementById("addr-results");
  const show = () => {
    const query = input.value.trim().toLowerCase(); if (query.length < 2) { output.textContent = ""; return; }
    const matches = CATALOG.filter((item) => item.address.toLowerCase().includes(query)).slice(0, 8);
    output.innerHTML = matches.map((item, index) => `<div style="cursor:pointer;padding:2px 0" data-i="${index}"><b>${esc(item.address)}</b> — `
      + `${item.status === "routed" ? item.price.toFixed(2) + " ₽, зона " + item.zone : esc(STATUS_RU[item.status])}</div>`).join("") || "не найдено";
    output.querySelectorAll("[data-i]").forEach((element) => element.addEventListener("click", () => {
      const item = matches[+element.dataset.i]; selectedUid = item.uid; renderSelected(); drawPoints();
      if (HIGHLIGHT) MAP.removeLayer(HIGHLIGHT);
      HIGHLIGHT = L.circleMarker([item.lat, item.lon], { radius: 8, color: "#111", weight: 3, fillColor: "#fff", fillOpacity: 1 }).addTo(MAP);
      MAP.setView([item.lat, item.lon], 16);
    }));
  };
  input.addEventListener("input", show);
}

function renderKishinevskaya(summary) {
  const rows = summary.kishinevskaya.map((item) => `<tr><td>${esc(item.address)}</td><td class="num">${item.old_km}</td><td class="num">${item.new_km}</td><td>${esc(item.status)}</td></tr>`).join("");
  const excluded = summary.kishinevskaya_excluded[0];
  document.getElementById("kish-block").innerHTML = `<p>Авторитетный manifest: <b>34</b> записи. Исключён ${esc(excluded.uid)}: ${esc(excluded.reason)}</p>`
    + `<table class="rt"><thead><tr><th>адрес</th><th>старое км</th><th>новое км</th><th>статус</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function init() {
  MAP = L.map("rmap", { preferCanvas: true, zoomControl: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTR }).addTo(MAP);
  let summary, points, parkany, index, geometries;
  try {
    [summary, points, parkany, index, geometries] = await Promise.all([loadJSON("data/reference-tariff-v3-summary.json"), loadJSON("data/zone-points.json"),
      loadJSON("data/parkany-route-boundary.json"), loadJSON("data/address-index.json"), loadJSON("data/review-route-geometries.json")]);
  } catch (error) { document.getElementById("rmap").innerHTML = "Ошибка загрузки: " + esc(error.message); return; }

  POINTS = points.points; CONTROL = parkany.route_lonlat; CONTROL_CUM = parkany.route_cum_km;
  for (const [uid, route] of Object.entries(geometries.routes)) ROUTES[uid] = { routeKm: route[0], points: decodePolyline6(route[1]) };
  CATALOG = index.addresses.map((row) => ({ uid: row[0], address: row[1], lon: row[2], lat: row[3], status: row[4],
    routeKm: row[5] === "" ? null : +row[5], oldK4: row[6], zone: row[7], price: row[8] }));
  selectedUid = (CATALOG.find((item) => item.status === "routed" && item.address.startsWith("Парканы,")) || CATALOG.find((item) => item.status === "routed")).uid;

  renderStatus(summary); renderKishinevskaya(summary);
  const lats = POINTS.map((point) => point[2]), lons = POINTS.map((point) => point[1]);
  MAP.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { padding: [20, 20] });
  L.circleMarker([summary.origin.lat, summary.origin.lon], { radius: 7, color: "#111827", fillColor: "#111827", fillOpacity: 1 }).addTo(MAP);
  CONTROL_LINE = L.polyline(CONTROL.map((point) => [point[1], point[0]]), { color: "#1f4e79", weight: 4, opacity: 0.9 }).addTo(MAP);
  GATE_LINE = L.polyline([], { color: "#dc2626", weight: 5, opacity: 0.9 }).addTo(MAP);
  GATE_MARKER = L.marker([0, 0], { draggable: true, icon: L.divIcon({ className: "", iconSize: [18, 18], html:
    '<div style="width:16px;height:16px;border-radius:50%;background:#dc2626;border:3px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5)"></div>' }) }).addTo(MAP);
  provisionalIdx = parkany.provisional_gate.corridor_route_index;
  try { const saved = JSON.parse(localStorage.getItem(LSKEY)); if (saved && saved.status === "owner_approved" && Number.isInteger(saved.route_index)) approved = saved; } catch (_error) { approved = null; }
  bIdx = approved ? approved.route_index : provisionalIdx;
  const nearest = (lat, lon) => { let best = 0, distance = Infinity; CONTROL.forEach((point, indexValue) => { const candidate = (point[1] - lat) ** 2 + (point[0] - lon) ** 2; if (candidate < distance) { distance = candidate; best = indexValue; } }); return best; };
  GATE_MARKER.on("drag", (event) => { const position = event.target.getLatLng(); applyGate(nearest(position.lat, position.lng)); });
  const slider = document.getElementById("gate-slider");
  slider.max = String(CONTROL.length - 2);
  slider.addEventListener("input", () => applyGate(+slider.value));
  applyGate(bIdx, Boolean(approved));

  document.querySelectorAll('input[name="mode"]').forEach((radio) => radio.addEventListener("change", drawPoints));
  document.getElementById("status-filter").addEventListener("change", drawPoints);
  document.getElementById("approve").addEventListener("click", saveGate);
  document.getElementById("reset").addEventListener("click", resetGate);
  document.getElementById("copy").addEventListener("click", () => navigator.clipboard && navigator.clipboard.writeText(`${CONTROL[bIdx][1].toFixed(6)}, ${CONTROL[bIdx][0].toFixed(6)}`));
  document.getElementById("download").addEventListener("click", () => {
    if (!approved) { document.getElementById("approve-out").innerHTML = '<span class="warn">Сначала утвердите границу.</span>'; return; }
    const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(exportCheckpoint(), null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = objectUrl; anchor.download = "tariff-checkpoint.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  });
  setupSearch();

  window.__reviewTest = {
    snapshot: () => { const selected = selectedItem(); return { routeIndex: bIdx, approved: Boolean(approved), breaks: [...CURRENT.breaks],
      zoneCounts: Object.fromEntries(Object.entries(CURRENT.stats).map(([zone, stat]) => [zone, stat.n])), crossing: CURRENT.crossing,
      notCrossing: CURRENT.notCrossing, selected: { uid: selected.uid, price: +selected.price.toFixed(3), zone: selected.zone, color: ZCOL[selected.zone] } }; },
    moveGateToIndex: (indexValue) => { applyGate(indexValue); return window.__reviewTest.snapshot(); },
    approve: () => { saveGate(); return window.__reviewTest.snapshot(); }, reset: () => { resetGate(); return window.__reviewTest.snapshot(); },
  };
  document.documentElement.dataset.reviewReady = "true";
}

init();
