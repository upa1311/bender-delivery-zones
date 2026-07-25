/* Final catalog page: filter-driven table + a VIEWPORT/GRID-CLUSTERED map.
 * The same filter drives the table and the map. The map never holds ~23k live
 * DOM markers: only points inside the current viewport are rendered, and when
 * there are too many they are aggregated into grid-cell clusters. Zone colours
 * are the permanent scheme, identical in polygons, points, legend and cards.
 * No runtime CDN — Leaflet is vendored. No prices shown. */
"use strict";

const ZC = { 1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828" };
const STATUS_COLOR = { disputed: "#7c3aed", no_delivery: "#9ca3af", excluded: "#6b7280" };
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";
const MAX_ROWS = 800;              // table render cap
const POINT_THRESHOLD = 1400;      // above this in-viewport, cluster into a grid
const GRID_CELLS = 46;             // grid resolution across the viewport

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

function colorOf(p) {
  if (p.zone_id && ZC[p.zone_id]) return ZC[p.zone_id];
  return STATUS_COLOR[p.service_status] || "#6b7280";
}

const map = L.map("cat-map", { preferCanvas: true }).setView([46.83, 29.48], 12);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);

const pointLayer = L.layerGroup().addTo(map);   // clusters / individual points
let highlight = null;
const overlays = {};                            // id -> Leaflet layer
let all = [];                                    // address rows
let sortKey = "settlement_ru", sortDir = 1;
let renderScheduled = false;

const hnKey = (h) => {
  const t = (h || "").trim();
  const m = t.match(/^\d+/);
  return [m ? parseInt(m[0], 10) : 1e9, t];
};

async function loadJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(p + " " + r.status);
  return r.json();
}

/* ---------- filters (drive BOTH table and map) ---------- */

function buildFilters() {
  const settlements = [...new Set(all.map((r) => r.settlement_ru).filter(Boolean))].sort();
  const fs = document.getElementById("f-settlement");
  settlements.forEach((s) => fs.add(new Option(s, s)));
  refreshDistricts();
}
function refreshDistricts() {
  const s = document.getElementById("f-settlement").value;
  const fd = document.getElementById("f-district");
  const cur = fd.value;
  fd.innerHTML = '<option value="">— район —</option>';
  const districts = [...new Set(all.filter((r) => !s || r.settlement_ru === s)
    .map((r) => r.district_ru).filter(Boolean))].sort();
  districts.forEach((d) => fd.add(new Option(d, d)));
  if (districts.includes(cur)) fd.value = cur;
}

function statusClass(r) {
  if (r.service_status === "disputed") return "disputed";
  if (r.service_status === "no_delivery") return "no_delivery";
  if (r.service_status === "excluded") return "excluded";
  if (r.address_status === "unaddressed_delivery_unit") return "unaddressed";
  return "verified";
}

function currentFilter() {
  const qs = document.getElementById("q-street").value.trim().toLowerCase();
  const qh = document.getElementById("q-house").value.trim().toLowerCase();
  const st = document.getElementById("f-settlement").value;
  const di = document.getElementById("f-district").value;
  const zones = new Set([...document.querySelectorAll(".fz:checked")].map((c) => +c.value));
  const showVerified = document.getElementById("s-verified").checked;
  const showUnaddressed = document.getElementById("s-unaddressed").checked;
  const showNoDelivery = document.getElementById("s-nodelivery").checked;
  const showDisputed = document.getElementById("s-disputed").checked;
  const showExcluded = document.getElementById("s-excluded").checked;
  return (r) => {
    if (qs && !(r.street_ru || "").toLowerCase().includes(qs)) return false;
    if (qh && !(r.housenumber || "").toLowerCase().includes(qh)) return false;
    if (st && r.settlement_ru !== st) return false;
    if (di && r.district_ru !== di) return false;
    const cls = statusClass(r);
    if (cls === "disputed") return showDisputed;
    if (cls === "no_delivery") return showNoDelivery;
    if (cls === "excluded") return showExcluded;
    if (cls === "unaddressed") return showUnaddressed && (!r.zone_id || zones.has(r.zone_id));
    if (!showVerified) return false;
    return r.zone_id ? zones.has(r.zone_id) : false;
  };
}

/* ---------- table ---------- */

function renderTable(rows) {
  const body = document.getElementById("cat-body");
  const sorted = rows.slice().sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (sortKey === "housenumber") {
      const ka = hnKey(x), kb = hnKey(y);
      return sortDir * (ka[0] - kb[0] || ka[1].localeCompare(kb[1]));
    }
    if (sortKey === "zone_id" || sortKey === "expected_km") {
      return sortDir * ((x || 0) - (y || 0));
    }
    return sortDir * String(x || "").localeCompare(String(y || ""));
  });
  body.innerHTML = sorted.slice(0, MAX_ROWS).map((r) => {
    const house = r.housenumber
      ? esc(r.housenumber)
      : '<span class="house-unconfirmed">Дом не подтверждён</span>';
    const zchip = r.zone_id
      ? `<span class="zchip z${r.zone_id}">Zone ${r.zone_id}</span>`
      : `<span class="zchip ${r.service_status === "disputed" ? "zdisp" : "znd"}">${esc(r.service_status)}</span>`;
    return `<tr data-uid="${esc(r.uid)}">
      <td>${esc(r.settlement_ru)}</td><td>${esc(r.district_ru || "")}</td>
      <td>${esc(r.street_ru || "")}</td><td>${house}</td>
      <td>${zchip}</td><td>${r.expected_km != null ? r.expected_km : "—"}</td>
      <td>${esc(r.service_status)}</td></tr>`;
  }).join("");
  document.getElementById("cat-count").textContent =
    `${rows.length} объектов${rows.length > MAX_ROWS ? ` (в таблице первые ${MAX_ROWS})` : ""}`;
}

/* ---------- viewport / grid clustered map ---------- */

function renderMap(rows) {
  pointLayer.clearLayers();
  const b = map.getBounds();
  const inView = rows.filter((r) => r.lat != null && b.contains([r.lat, r.lon]));

  if (inView.length <= POINT_THRESHOLD) {
    for (const r of inView) {
      L.circleMarker([r.lat, r.lon], {
        radius: 3, weight: 0, fillColor: colorOf(r), fillOpacity: 0.85,
      }).on("click", () => focusUid(r.uid)).addTo(pointLayer);
    }
    return;
  }

  // Aggregate into viewport grid cells; render one marker per non-empty cell.
  const sw = b.getSouthWest(), ne = b.getNorthEast();
  const dLat = (ne.lat - sw.lat) / GRID_CELLS || 1e-9;
  const dLon = (ne.lng - sw.lng) / GRID_CELLS || 1e-9;
  const cells = new Map();
  for (const r of inView) {
    const gy = Math.floor((r.lat - sw.lat) / dLat);
    const gx = Math.floor((r.lon - sw.lng) / dLon);
    const key = gy * (GRID_CELLS + 1) + gx;
    let cell = cells.get(key);
    if (!cell) {
      cell = { n: 0, sLat: 0, sLon: 0, zoneCount: {} };
      cells.set(key, cell);
    }
    cell.n += 1;
    cell.sLat += r.lat;
    cell.sLon += r.lon;
    const z = r.zone_id || r.service_status;
    cell.zoneCount[z] = (cell.zoneCount[z] || 0) + 1;
  }
  for (const cell of cells.values()) {
    const lat = cell.sLat / cell.n, lon = cell.sLon / cell.n;
    const dominant = Object.entries(cell.zoneCount).sort((a, b) => b[1] - a[1])[0][0];
    const color = ZC[dominant] || STATUS_COLOR[dominant] || "#4b5563";
    const radius = Math.min(22, 8 + Math.log2(cell.n) * 2.4);
    L.circleMarker([lat, lon], {
      radius, weight: 1, color: "#1f2937", fillColor: color, fillOpacity: 0.7,
    })
      .bindTooltip(String(cell.n), { permanent: cell.n < 1000, direction: "center",
        className: "cluster-count" })
      .on("click", () => map.setView([lat, lon], Math.min(map.getZoom() + 2, 18)))
      .addTo(pointLayer);
  }
}

function scheduleRender() {
  if (renderScheduled) return;
  renderScheduled = true;
  requestAnimationFrame(() => {
    renderScheduled = false;
    const rows = all.filter(currentFilter());
    renderTable(rows);
    renderMap(rows);
  });
}

/* ---------- house card ---------- */

function houseCard(r) {
  const card = document.getElementById("house-card");
  const full = r.housenumber
    ? [r.settlement_ru, r.district_ru, r.street_ru, "дом " + r.housenumber].filter(Boolean).join(", ")
    : "Дом не подтверждён";
  card.innerHTML = `<span class="close">×</span>
    <h3>${esc(full)}</h3>
    <table>
      <tr><td class="k">населённый пункт</td><td>${esc(r.settlement_ru || "—")}</td></tr>
      <tr><td class="k">район</td><td>${esc(r.district_ru || "—")}</td></tr>
      <tr><td class="k">улица</td><td>${esc(r.street_ru || "—")}</td></tr>
      <tr><td class="k">дом</td><td>${r.housenumber ? esc(r.housenumber) : "не подтверждён"}</td></tr>
      <tr><td class="k">зона</td><td>${r.zone_id ? "Zone " + r.zone_id : "—"}</td></tr>
      <tr><td class="k">central_km</td><td>${r.central_km ?? "—"}</td></tr>
      <tr><td class="k">bam_km</td><td>${r.bam_km ?? "—"}</td></tr>
      <tr><td class="k">expected_km</td><td>${r.expected_km ?? "—"}</td></tr>
      <tr><td class="k">service_status</td><td>${esc(r.service_status)}</td></tr>
      <tr><td class="k">address_status</td><td>${esc(r.address_status)}</td></tr>
      <tr><td class="k">источник</td><td>OSM ${esc((r.osm_type || "") + (r.osm_id ?? ""))}</td></tr>
      <tr><td class="k">набор данных</td><td>${esc(r.source_dataset_version || "—")}</td></tr>
      <tr><td class="k">owner_review</td><td>${r.owner_review_required ?? "—"}</td></tr>
    </table>
    <p class="muted small">Стоимость доставки не отображается.</p>`;
  card.hidden = false;
  card.querySelector(".close").onclick = () => { card.hidden = true; };
}

function focusUid(uid) {
  const r = all.find((x) => x.uid === uid);
  if (!r || r.lat == null) return;
  document.querySelectorAll("#cat-body tr").forEach((tr) =>
    tr.classList.toggle("active", tr.dataset.uid === uid));
  map.setView([r.lat, r.lon], 17);
  if (highlight) map.removeLayer(highlight);
  highlight = L.circleMarker([r.lat, r.lon], {
    radius: 11, color: "#111827", weight: 3, fillColor: colorOf(r), fillOpacity: 0.9,
  }).addTo(map);
  houseCard(r);
}

/* ---------- overlays ---------- */

function toggleOverlay(id, layer) {
  overlays[id] = layer;
  const checkbox = document.getElementById(id);
  const apply = () => {
    if (checkbox.checked) layer.addTo(map);
    else map.removeLayer(layer);
  };
  checkbox.addEventListener("change", apply);
  apply();
}

async function init() {
  try {
    const [polys, points, tierc, vVillage, vAdmin, sevRoute] = await Promise.all([
      loadJSON("data/final-zone-polygons.geojson"),
      loadJSON("data/final-address-zone-points.geojson"),
      loadJSON("data/tier-c-manual-review.geojson"),
      loadJSON("data/varnita-village-no-delivery.geojson"),
      loadJSON("data/varnita-admin-reference.geojson"),
      loadJSON("data/severny-route-qa.geojson"),
    ]);

    L.geoJSON(polys, {
      style: (f) => ({ color: "#1f2937", weight: 2,
        fillColor: f.properties.color, fillOpacity: 0.22 }),
      onEachFeature: (f, l) => l.bindPopup(
        `<b>${f.properties.zone_name}</b><br>${esc(f.properties.component)}`),
    }).addTo(map);

    all = points.features.map((f) => ({ ...f.properties,
      lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }));

    // toggleable QA overlays (grey Varnița, dashed admin line, Северный routes, Tier C)
    toggleOverlay("ov-varnita-village", L.geoJSON(vVillage, {
      style: () => ({ color: "#4b5563", weight: 1.5, fillColor: "#9ca3af",
        fillOpacity: 0.5 }) }));
    toggleOverlay("ov-varnita-admin", L.geoJSON(vAdmin, {
      style: () => ({ color: "#6b7280", weight: 2, dashArray: "8 6", fill: false }) }));
    toggleOverlay("ov-severny-route", L.geoJSON(sevRoute, {
      style: () => ({ color: "#0e9488", weight: 2 }) }));
    toggleOverlay("ov-tierc", L.geoJSON(tierc, {
      style: () => ({ color: "#b45309", weight: 3, dashArray: "4 5" }),
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 5, color: "#b45309",
        fillColor: "#f59e0b", fillOpacity: 0.6 }) }));

    buildFilters();
    scheduleRender();

    ["q-street", "q-house", "f-settlement", "f-district", "s-verified",
      "s-unaddressed", "s-nodelivery", "s-disputed", "s-excluded"]
      .forEach((id) => document.getElementById(id).addEventListener("input", () => {
        if (id === "f-settlement") refreshDistricts();
        scheduleRender();
      }));
    document.querySelectorAll(".fz").forEach((c) => c.addEventListener("change", scheduleRender));
    map.on("moveend zoomend", scheduleRender);
    document.querySelectorAll("#cat-table thead th").forEach((th) =>
      th.addEventListener("click", () => {
        const k = th.dataset.sort;
        sortDir = (sortKey === k) ? -sortDir : 1; sortKey = k; scheduleRender();
      }));
    document.getElementById("cat-body").addEventListener("click", (e) => {
      const tr = e.target.closest("tr"); if (tr) focusUid(tr.dataset.uid);
    });
  } catch (err) {
    document.getElementById("cat-count").textContent = "Ошибка загрузки: " + err.message;
    console.error(err);
  }
}

init();
