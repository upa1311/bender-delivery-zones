/* Public delivery-zones map.
 *
 * PRIMARY layer (always on by default): the 4 final K=4 delivery zones from
 *   data/final-zone-polygons.geojson
 * styled with the colours/edges from
 *   data/final-zone-map-summary.json
 *
 * The GeoJSON has 5 polygon features because Zone 4 also has a separate
 * `severny_enclave` component — it is still Zone 4. Geometry is rendered exactly
 * as stored (no hand-drawing, no circles, no geometry edits).
 *
 * All the older QA/verification layers are kept but are OFF by default, in a
 * collapsed "Дополнительные слои" control. Address search and the catalog link
 * are preserved. Tariffs/routing are not configured. OSM raster tiles are the
 * only external request; data © OpenStreetMap contributors. */
"use strict";

const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

const map = L.map("map", { zoomControl: true }).setView([46.8218, 29.4819], 12);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: OSM_ATTRIBUTION,
}).addTo(map);

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

/* ---------- zone helpers ---------- */

const COMPONENT_RU = {
  bender_main: "Бендеры (основной массив)",
  severny_enclave: "Северный (анклав Zone 4)",
};

/** "до X км" for the innermost band (min null), otherwise "A–B км". */
function zoneRangeText(p) {
  const lo = p.band_min_km == null ? 0 : p.band_min_km;
  if (p.band_min_km == null) return `до ${p.band_max_km} км`;
  return `${lo}–${p.band_max_km} км`;
}

function zonePopup(p) {
  const minTxt = p.band_min_km == null ? "0 (центр)" : `${p.band_min_km} км`;
  return `<div class="popup">
    <div class="popup-title">${esc(p.zone_name)}
      <span class="badge review">тариф не назначен</span></div>
    <table>
      <tr><td class="k">минимальное расстояние</td><td>${minTxt}</td></tr>
      <tr><td class="k">максимальное расстояние</td><td>${p.band_max_km} км</td></tr>
      <tr><td class="k">компонент</td><td>${esc(COMPONENT_RU[p.component] || p.component)}</td></tr>
    </table>
    ${p.note ? `<p class="muted small">${esc(p.note)}</p>` : ""}
  </div>`;
}

function renderZoneLegend(summary, zones) {
  const byId = {};
  zones.features.forEach((f) => { byId[f.properties.zone_id] = f.properties; });
  const ul = document.getElementById("zone-legend");
  const ids = Object.keys(byId).map(Number).sort((a, b) => a - b);
  ul.innerHTML = ids.map((id) => {
    const p = byId[id];
    const color = (summary.zone_colors && summary.zone_colors[id]) || p.color;
    return `<li><span class="swatch" style="background:${color}33;border:2px solid ${color}"></span>`
      + `<span><b>${esc(p.zone_name)}</b> — ${esc(zoneRangeText(p))}</span></li>`;
  }).join("")
    + `<li class="muted small" style="margin-top:6px">Zone 4 включает анклав «Северный».</li>`;
}

/* ---------- search (preserved) ---------- */

const SETTLEMENT_OF = {
  bender_core: "Бендеры", bender_lipcani: "Бендеры",
  giska: "Гиска", parkany: "Парканы", protyagailovka: "Протягайловка",
};
let roadFeatures = [];
const searchHighlight = L.layerGroup().addTo(map);

function streetPopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.ru_display || p.name)}</div>
    <table>
      <tr><td class="k">населённый пункт</td><td>${esc(p.settlement_ru || SETTLEMENT_OF[p.settlement] || "—")}</td></tr>
      <tr><td class="k">исходное</td><td>${esc(p.name)}</td></tr>
      ${p["name:ru"] ? `<tr><td class="k">name:ru</td><td>${esc(p["name:ru"])}</td></tr>` : ""}
      ${p["name:ro"] ? `<tr><td class="k">name:ro</td><td>${esc(p["name:ro"])}</td></tr>` : ""}
    </table></div>`;
}

function setupSearch() {
  const input = document.getElementById("street-search");
  const out = document.getElementById("search-results");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    searchHighlight.clearLayers();
    if (q.length < 2) { out.textContent = ""; return; }
    const matches = roadFeatures.filter((f) => {
      const p = f.properties;
      return [p.name, p["name:ru"], p.ru_display, p["name:ro"]]
        .some((v) => v && String(v).toLowerCase().includes(q));
    });
    const places = new Map();
    matches.forEach((f) => {
      const p = f.properties;
      const place = p.settlement_ru || SETTLEMENT_OF[p.settlement] || "—";
      places.set(`${p.ru_display || p.name}||${place}`,
        (places.get(`${p.ru_display || p.name}||${place}`) || 0) + 1);
    });
    const variants = [...places.entries()].sort().map(([key, n]) => {
      const [street, place] = key.split("||");
      return `<div class="variant"><b>${esc(street)}</b><br>`
        + `<span class="muted small">${esc(place)} · ${n} сегм.</span></div>`;
    }).join("");
    out.innerHTML = `Найдено улиц (сегментов): ${matches.length}` + variants;
    if (!matches.length) return;
    const hl = L.geoJSON({ type: "FeatureCollection", features: matches }, {
      style: () => ({ color: "#111827", weight: 5, opacity: 1 }),
      onEachFeature: (feat, lyr) => lyr.bindPopup(streetPopup(feat.properties)),
    });
    searchHighlight.addLayer(hl);
    try { map.fitBounds(hl.getBounds(), { maxZoom: 16, padding: [30, 30] }); } catch (e) { /* empty */ }
  });
}

/* ---------- optional QA overlays (OFF by default, collapsed control) ---------- */

async function addExtraLayers(control) {
  const load = async (path) => { try { return await loadJSON(path); } catch (e) { return null; } };
  const add = (name, data, opts) => {
    if (!data) return;
    control.addOverlay(L.geoJSON(data, opts), name); // not added to map => OFF by default
  };

  const source = await load("data/source-boundaries.geojson");
  add("Исходные границы OSM (справочно)", source, {
    style: () => ({ color: "#6b7280", weight: 2, dashArray: "7 6", fill: false, opacity: 0.9 }),
    onEachFeature: (f, l) => l.bindPopup(
      `<div class="popup"><div class="popup-title">${esc(f.properties.display_ru || "Граница OSM")}</div>`
      + `<p class="muted small">${esc(f.properties.note || "")}</p></div>`),
  });

  const tierC = await load("data/tier-c-manual-review.geojson");
  add("Tier C — не обслуживается", tierC, {
    style: () => ({ color: "#b45309", weight: 5, dashArray: "4 5", opacity: 0.95 }),
    onEachFeature: (f, l) => l.bindPopup(
      `<div class="popup"><div class="popup-title">${esc(f.properties.street_ru || "Tier C")}`
      + ` <span class="badge review">не обслуживается</span></div></div>`),
  });

  const questions = await load("data/boundary-questions.geojson");
  add("Спорные адреса", questions, {
    pointToLayer: (f, latlng) => L.circleMarker(latlng, {
      radius: 7, color: "#d1461f", fillColor: "#fff", fillOpacity: 1, weight: 3 }),
    onEachFeature: (f, l) => l.bindPopup(
      `<div class="popup"><div class="popup-title">Спорное место</div>`
      + `<p>${esc(f.properties.question || "")}</p></div>`),
  });

  const severnyRoutes = await load("data/severny-route-qa.geojson");
  add("Северный — маршруты (QA)", severnyRoutes, {
    style: () => ({ color: "#0ea5e9", weight: 3, opacity: 0.85, dashArray: "5 4" }),
    onEachFeature: (f, l) => l.bindPopup(
      `<div class="popup"><b>Маршрут «Северный»</b><br>${esc(f.properties.name || "")}</div>`),
  });

  const varnita = await load("data/varnita-village-no-delivery.geojson");
  add("Варница (село) — без доставки", varnita, {
    style: () => ({ color: "#4b5563", weight: 1.5, fillColor: "#9ca3af", fillOpacity: 0.55 }),
    onEachFeature: (f, l) => l.bindPopup(
      `<div class="popup"><div class="popup-title">Варница (село)</div>`
      + `<p class="muted small">${esc(f.properties.note || "")}</p></div>`),
  });
}

/* ---------- init ---------- */

async function init() {
  try {
    const [summary, zones] = await Promise.all([
      loadJSON("data/final-zone-map-summary.json"),
      loadJSON("data/final-zone-polygons.geojson"),
    ]);

    // PRIMARY: the 4 final K=4 zones (5 features; Zone 4 = main + Северный).
    const zoneLayer = L.geoJSON(zones, {
      style: (f) => ({
        color: f.properties.color,
        weight: 2.5,
        opacity: 1,
        fillColor: f.properties.color,
        fillOpacity: 0.35,
      }),
      onEachFeature: (f, l) => l.bindPopup(zonePopup(f.properties)),
    }).addTo(map);

    // Permanent labels: Zone 1..4 on the main component; Северный on the enclave.
    // Zones 1..4 are concentric bands sharing a bbox centre, so their labels would
    // pile up; place each along its own east edge (inner→outer spreads eastwards).
    const labelLayer = L.layerGroup().addTo(map);
    zones.features.forEach((f) => {
      const p = f.properties;
      const b = L.geoJSON(f).getBounds();
      const c = b.getCenter();
      const isSeverny = p.component === "severny_enclave";
      // Concentric bands share a centre; give each a distinct compass anchor inside
      // its own band so the four labels never overlap. Северный keeps its centroid.
      const dir = { 1: "w", 2: "n", 3: "e", 4: "s" }[p.zone_id] || "c";
      const at = isSeverny ? c : L.latLng(
        dir === "n" ? c.lat + 0.55 * (b.getNorth() - c.lat)
          : dir === "s" ? c.lat - 0.55 * (c.lat - b.getSouth()) : c.lat,
        dir === "e" ? c.lng + 0.55 * (b.getEast() - c.lng)
          : dir === "w" ? c.lng - 0.55 * (c.lng - b.getWest()) : c.lng);
      L.marker(at, {
        interactive: false,
        icon: L.divIcon({
          className: isSeverny ? "zone-label zone-label-severny" : "zone-label",
          html: `<span style="--c:${p.color}">`
            + `${esc(isSeverny ? "Zone 4 · Северный" : p.zone_name)}</span>`,
          iconSize: [0, 0],
        }),
      }).addTo(labelLayer);
    });

    // Auto fitBounds over ALL zone polygons, including Северный. Re-fit after the
    // flex layout has sized the container (avoids a degenerate zero-height fit).
    const zoneBounds = zoneLayer.getBounds();
    const fitZones = () => {
      map.invalidateSize();
      try { map.fitBounds(zoneBounds, { padding: [30, 30] }); } catch (e) { /* empty */ }
    };
    fitZones();
    requestAnimationFrame(fitZones);
    window.addEventListener("load", fitZones);

    renderZoneLegend(summary, zones);

    // Collapsed "extra layers" control (all OFF by default). Zones stay always-on
    // and are also listed (checked) so users understand they are the base view.
    const control = L.control.layers(null, { "Зоны доставки K=4": zoneLayer },
      { collapsed: true }).addTo(map);
    await addExtraLayers(control);

    // Preserve street search (best-effort; does not block the zones).
    try {
      const roads = await loadJSON("data/roads.geojson");
      roadFeatures = roads.features;
      control.addOverlay(L.geoJSON(roads, {
        style: () => ({ color: "#6b7280", weight: 1.2, opacity: 0.7 }),
        onEachFeature: (f, l) => l.bindPopup(streetPopup(f.properties)),
      }), "Улицы");
      setupSearch();
    } catch (e) {
      const out = document.getElementById("search-results");
      if (out) out.textContent = "Поиск улиц недоступен.";
    }
  } catch (err) {
    const ul = document.getElementById("zone-legend");
    if (ul) ul.innerHTML = `<li class="muted">Ошибка загрузки зон: ${esc(err.message)}</li>`;
    console.error(err);
  }
}

init();
