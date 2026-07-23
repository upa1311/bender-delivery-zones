/* Service-area QA map. All data is loaded from the local extract outputs in
 * ./data/. OSM raster tiles are used only as a background, with attribution.
 * This map does NOT define delivery zones, tariffs, or routing. */
"use strict";

const START = { lat: 46.8218, lon: 29.4819, zoom: 13 }; // Bender
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";
const SETTLEMENT_LABEL = {
  bender: "Бендеры",
  protyagailovka: "Протягайловка",
  giska: "Гиска",
  parkany: "Парканы",
};
const SETTLEMENT_COLOR = {
  bender: "#2f6fed",
  protyagailovka: "#1f9d55",
  giska: "#e8730c",
  parkany: "#7c3aed",
};

const map = L.map("map", { zoomControl: true }).setView([START.lat, START.lon], START.zoom);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: OSM_ATTRIBUTION,
}).addTo(map);

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

function fieldRows(props, keys) {
  return keys
    .filter((k) => props[k])
    .map((k) => `<tr><td class="k">${esc(k)}</td><td>${esc(props[k])}</td></tr>`)
    .join("");
}

function settlementPopup(p) {
  const badge = p.status === "boundary_found"
    ? '<span class="badge found">граница найдена</span>'
    : '<span class="badge missing">граница отсутствует</span>';
  return `<div class="popup">
    <div class="popup-title">${esc(p.display_ru)} ${badge}</div>
    <table>
      <tr><td class="k">OSM</td><td>${esc(p.osm_type)} ${esc(p.osm_id)}</td></tr>
      <tr><td class="k">статус</td><td>${esc(p.status)}</td></tr>
      ${fieldRows(p, ["name", "name:ru", "name:ro", "official_name", "alt_name", "old_name"])}
    </table></div>`;
}

function streetPopup(p) {
  const badge = p.ru_status === "needs_ru_review"
    ? '<span class="badge review">нужна проверка RU</span>'
    : '<span class="badge ok">RU подтверждено</span>';
  return `<div class="popup">
    <div class="popup-title">${esc(p.ru_display || p.name)} ${badge}</div>
    <table>
      <tr><td class="k">исходное</td><td>${esc(p.name)}</td></tr>
      ${fieldRows(p, ["name:ru", "name:ro", "official_name", "alt_name", "old_name"])}
      <tr><td class="k">RU источник</td><td>${esc(p.ru_source)}</td></tr>
      <tr><td class="k">OSM</td><td>${esc(p.osm_type)} ${esc(p.osm_id)}</td></tr>
    </table></div>`;
}

const layers = {}; // settlement key -> L.layerGroup
const overlays = {}; // russian label -> layer
let roadsLayer, reviewLayer;
let roadFeatures = [];
let searchHighlight = L.layerGroup().addTo(map);

function boundaryStyle(key) {
  return { color: SETTLEMENT_COLOR[key] || "#333", weight: 2, fillColor: SETTLEMENT_COLOR[key],
           fillOpacity: 0.12 };
}

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function buildSettlements(fc) {
  fc.features.forEach((f) => {
    const key = f.properties.key;
    let layer;
    if (f.geometry && f.geometry.type !== "Point") {
      layer = L.geoJSON(f, { style: () => boundaryStyle(key) });
    } else if (f.geometry && f.geometry.type === "Point") {
      const [lon, lat] = f.geometry.coordinates;
      layer = L.circleMarker([lat, lon], {
        radius: 9, color: "#d1461f", fillColor: "#d1461f", fillOpacity: 0.9,
      });
    } else {
      return; // no geometry at all
    }
    layer.bindPopup(settlementPopup(f.properties));
    const group = L.layerGroup([layer]).addTo(map);
    layers[key] = group;
    overlays[SETTLEMENT_LABEL[key] || key] = group;
  });
}

function buildRoads(fc) {
  roadFeatures = fc.features;
  roadsLayer = L.geoJSON(fc, {
    style: () => ({ color: "#6b7280", weight: 1.6, opacity: 0.85 }),
    onEachFeature: (feat, lyr) => lyr.bindPopup(streetPopup(feat.properties)),
  }).addTo(map);

  const reviewFC = { type: "FeatureCollection",
    features: fc.features.filter((f) => f.properties.ru_status === "needs_ru_review") };
  reviewLayer = L.geoJSON(reviewFC, {
    style: () => ({ color: "#e0451f", weight: 4, opacity: 0.95 }),
    onEachFeature: (feat, lyr) => lyr.bindPopup(streetPopup(feat.properties)),
  }).addTo(map);

  overlays["Дороги"] = roadsLayer;
  overlays["Улицы без русского названия"] = reviewLayer;
}

function renderStats(summary) {
  const t = summary.totals;
  const kpi = [
    ["Населённых пунктов", t.settlements],
    ["Границы найдены", t.boundaries_found],
    ["Границы отсутствуют", t.boundaries_missing],
    ["Уникальных улиц", t.unique_streets],
    ["Улиц с name:ru", t.streets_with_name_ru],
    ["Требуют проверки RU", t.streets_needs_ru_review],
  ].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join("");

  let rows = "";
  Object.keys(summary.per_settlement).sort().forEach((key) => {
    const s = summary.per_settlement[key];
    rows += `<tr><td>${esc(s.display_ru)}</td>
      <td class="num">${s.unique_streets}</td>
      <td class="num">${s.streets_with_name_ru}</td>
      <td class="num">${s.streets_needs_ru_review}</td>
      <td class="num">${s.buildings}</td>
      <td class="num">${s.address_objects}</td></tr>`;
  });

  document.getElementById("stats-body").innerHTML = `
    ${kpi}
    <table>
      <thead><tr><th>Территория</th><th class="num">улиц</th><th class="num">RU</th>
        <th class="num">пров.</th><th class="num">здан.</th><th class="num">адр.</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function setupSearch() {
  const input = document.getElementById("street-search");
  const out = document.getElementById("search-results");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    searchHighlight.clearLayers();
    if (q.length < 2) { out.textContent = ""; return; }
    const matches = roadFeatures.filter((f) => {
      const p = f.properties;
      return [p.name, p["name:ru"], p.ru_display, p["name:ro"]]
        .some((v) => v && String(v).toLowerCase().includes(q));
    });
    out.textContent = `Найдено улиц (сегментов): ${matches.length}`;
    if (!matches.length) return;
    const hl = L.geoJSON({ type: "FeatureCollection", features: matches }, {
      style: () => ({ color: "#111827", weight: 5, opacity: 1 }),
      onEachFeature: (feat, lyr) => lyr.bindPopup(streetPopup(feat.properties)),
    });
    searchHighlight.addLayer(hl);
    try { map.fitBounds(hl.getBounds(), { maxZoom: 16, padding: [30, 30] }); } catch (e) { /* empty */ }
  });
}

async function init() {
  try {
    const [settlements, roads, summary] = await Promise.all([
      loadJSON("data/settlements.geojson"),
      loadJSON("data/roads.geojson"),
      loadJSON("data/summary.json"),
    ]);
    buildSettlements(settlements);
    buildRoads(roads);
    L.control.layers(null, overlays, { collapsed: false }).addTo(map);
    renderStats(summary);
    setupSearch();
  } catch (err) {
    document.getElementById("stats-body").textContent = "Ошибка загрузки данных: " + err.message;
    console.error(err);
  }
}

init();
