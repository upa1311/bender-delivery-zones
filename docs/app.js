/* Service-area QA map.
 *
 * Two distinct layers by design:
 *   - Source OSM boundaries  : dashed, unmodified administrative reference.
 *   - Candidate working area : solid, derived from residential density + owner limits.
 *
 * All data comes from the local OSM extract outputs in ./data/. OSM raster tiles
 * are used only as a background, with attribution. This map does NOT define
 * delivery zones, tariffs, or routing. */
"use strict";

const START = { lat: 46.8218, lon: 29.4819, zoom: 13 }; // Bender
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

const TERRITORY_LABEL = {
  bender_core: "Бендеры",
  bender_lipcani: "Липканы",
  protyagailovka: "Протягайловка",
  giska: "Гиска",
  parkany: "Парканы",
};
const TERRITORY_COLOR = {
  bender_core: "#2f6fed",
  bender_lipcani: "#0e9488",
  protyagailovka: "#1f9d55",
  giska: "#e8730c",
  parkany: "#7c3aed",
};
const EXCLUDED_COLOR = {
  farmland: "#c9a227",
  forest_or_park: "#3f8f4f",
  empty_land: "#9aa0a6",
  sparse_buildings: "#b45309",
  outside_owner_named_limit: "#d1461f",
};
const REASON_RU = {
  dense_residential_buildings: "плотная жилая застройка",
  addressed_buildings: "здания с адресами",
  residential_street: "жилая улица",
  required_access_road: "необходимый подъезд",
  owner_named_boundary: "предел, названный владельцем",
  farmland: "поля",
  forest_or_park: "лес/парк",
  empty_land: "пустая земля",
  sparse_buildings: "редкая застройка",
  outside_owner_named_limit: "вне предела владельца",
};

const map = L.map("map", { zoomControl: true }).setView([START.lat, START.lon], START.zoom);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: OSM_ATTRIBUTION,
}).addTo(map);

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
const ru = (r) => REASON_RU[r] || r;
const reasonList = (arr) => (arr || []).map((r) => `<code>${esc(ru(r))}</code>`).join(", ") || "—";

function fieldRows(props, keys) {
  return keys.filter((k) => props[k])
    .map((k) => `<tr><td class="k">${esc(k)}</td><td>${esc(props[k])}</td></tr>`).join("");
}

/* ---------- popups ---------- */

function candidatePopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.display_ru)} <span class="badge found">рабочая территория</span></div>
    <table>
      <tr><td class="k">площадь исходной границы</td><td>${p.source_area_km2} км²</td></tr>
      <tr><td class="k">площадь рабочей территории</td><td>${p.candidate_area_km2} км²</td></tr>
      <tr><td class="k">сокращение</td><td><b>${p.reduction_pct}%</b></td></tr>
      <tr><td class="k">зданий включено</td><td>${p.buildings_included}</td></tr>
      <tr><td class="k">зданий исключено</td><td>${p.buildings_excluded}</td></tr>
      <tr><td class="k">адресов внутри</td><td>${p.addresses_inside}</td></tr>
      <tr><td class="k">причины включения</td><td>${reasonList(p.inclusion_reasons)}</td></tr>
      <tr><td class="k">причины исключения</td><td>${reasonList(p.exclusion_reasons)}</td></tr>
      <tr><td class="k">OSM источник</td><td>relation ${esc(p.source_relation)}</td></tr>
    </table>
    <p class="muted small">Это кандидат рабочей территории, а не официальная граница.</p>
  </div>`;
}

function sourcePopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.display_ru)} <span class="badge">исходная граница OSM</span></div>
    <table>
      <tr><td class="k">OSM</td><td>${esc(p.osm_type)} ${esc(p.osm_id)}</td></tr>
      <tr><td class="k">площадь</td><td>${p.area_km2} км²</td></tr>
    </table>
    <p class="muted small">${esc(p.note)}</p></div>`;
}

function excludedPopup(p) {
  return `<div class="popup">
    <div class="popup-title">Исключено: ${esc(ru(p.reason))}</div>
    <table>
      ${p.name ? `<tr><td class="k">название</td><td>${esc(p.name)}</td></tr>` : ""}
      ${p.landuse ? `<tr><td class="k">landuse</td><td>${esc(p.landuse)}</td></tr>` : ""}
      <tr><td class="k">территория</td><td>${esc(TERRITORY_LABEL[p.territory] || p.territory)}</td></tr>
      <tr><td class="k">площадь</td><td>${(p.area_m2 / 10000).toFixed(2)} га</td></tr>
      ${p.note ? `<tr><td class="k">примечание</td><td>${esc(p.note)}</td></tr>` : ""}
    </table></div>`;
}

function sparsePopup(p) {
  return `<div class="popup">
    <div class="popup-title">Редкая застройка <span class="badge review">проверить</span></div>
    <table>
      <tr><td class="k">зданий в группе</td><td>${p.buildings}</td></tr>
      <tr><td class="k">территория</td><td>${esc(TERRITORY_LABEL[p.territory] || p.territory)}</td></tr>
    </table>
    <p class="muted small">${esc(p.note)}</p></div>`;
}

function questionPopup(p) {
  return `<div class="popup">
    <div class="popup-title">Спорное место <span class="badge review">${esc(p.kind)}</span></div>
    ${p.street ? `<p><b>${esc(p.street)}</b></p>` : ""}
    <p>${esc(p.question)}</p></div>`;
}

function streetPopup(p) {
  const badge = p.ru_status === "needs_ru_review"
    ? '<span class="badge review">нужна проверка RU</span>'
    : '<span class="badge ok">RU подтверждено</span>';
  const cls = p.is_address_street ? "адресная улица" : "не адресная улица";
  return `<div class="popup">
    <div class="popup-title">${esc(p.ru_display || p.name)} ${badge}</div>
    <table>
      <tr><td class="k">исходное</td><td>${esc(p.name)}</td></tr>
      ${fieldRows(p, ["name:ru", "name:ro", "official_name", "alt_name", "old_name"])}
      <tr><td class="k">RU источник</td><td>${esc(p.ru_source)}</td></tr>
      <tr><td class="k">класс</td><td>${esc(p.road_class)} — ${cls}</td></tr>
      <tr><td class="k">OSM</td><td>${esc(p.osm_type)} ${esc(p.osm_id)}</td></tr>
    </table></div>`;
}

/* ---------- layers ---------- */

const overlays = {};
const labelLayer = L.layerGroup().addTo(map);
const searchHighlight = L.layerGroup().addTo(map);
let roadFeatures = [];

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function addPermanentLabels(fc) {
  fc.features.forEach((f) => {
    const key = f.properties.key;
    const layer = L.geoJSON(f);
    const c = layer.getBounds().getCenter();
    L.marker(c, {
      interactive: false,
      icon: L.divIcon({
        className: "area-label",
        html: `<span style="--c:${TERRITORY_COLOR[key] || "#333"}">${esc(TERRITORY_LABEL[key] || key)}</span>`,
        iconSize: [0, 0],
      }),
    }).addTo(labelLayer);
  });
}

function tierCPopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.street_ru)}
      <span class="badge review">Tier C — не обслуживается</span></div>
    <table>
      <tr><td class="k">территория</td><td>${esc(TERRITORY_LABEL[p.settlement] || p.settlement)}</td></tr>
      <tr><td class="k">адресов</td><td>${p.confirmed_addresses}</td></tr>
      <tr><td class="k">вероятных жилых</td><td>${p.probable_residential_buildings}</td></tr>
      <tr><td class="k">связь с ядром</td><td>${p.connected_to_core ? "да" : "нет"}</td></tr>
      <tr><td class="k">до ядра по дорогам</td><td>${p.distance_to_core_by_road_km ?? "—"} км</td></tr>
      <tr><td class="k">причина</td><td><code>${esc(p.reason)}</code></td></tr>
      <tr><td class="k">влияет на тарифы</td><td><b>нет</b></td></tr>
    </table>
    <p class="muted small">${esc(p.note)}</p></div>`;
}

const ZONE_COLORS = ["#2f6fed", "#e8730c", "#1f9d55", "#7c3aed", "#d1461f"];

function zonePopup(p) {
  return `<div class="popup">
    <div class="popup-title">K=${p.k} · зона ${p.zone}
      <span class="badge review">черновик</span></div>
    <table>
      <tr><td class="k">адресов</td><td>${p.addresses}</td></tr>
      <tr><td class="k">вес спроса</td><td>${p.demand_weight}</td></tr>
      <tr><td class="k">медиана</td><td>${p.median_km} км · ${p.median_min} мин</td></tr>
      <tr><td class="k">p90 время</td><td>${p.p90_min} мин</td></tr>
      <tr><td class="k">компактность</td><td>${p.compactness}</td></tr>
      <tr><td class="k">площадь</td><td>${p.area_km2} км²</td></tr>
    </table>
    <p class="muted small">Время по свободному потоку (без пробок) — нижняя граница.
    Победитель K не выбран, цены не назначались.</p></div>`;
}

function originPopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.key)}</div>
    <table>
      <tr><td class="k">роль</td><td>${esc(p.role)}</td></tr>
      <tr><td class="k">доля заказов</td><td>${p.weight}</td></tr>
      <tr><td class="k">заведений в кластере</td><td>${p.poi_count}</td></tr>
    </table>
    <p class="muted small">${esc(p.note)}</p></div>`;
}

function kPopup(p) {
  return `<div class="popup">
    <div class="popup-title">K=${p.k} · кластер ${p.cluster}</div>
    <table>
      <tr><td class="k">взвешенный спрос</td><td>${p.weighted_demand}</td></tr>
      <tr><td class="k">улиц в кластере</td><td>${p.member_streets}</td></tr>
      <tr><td class="k">статус</td><td><code>${esc(p.status)}</code></td></tr>
    </table>
    <p class="muted small">Черновик. Победитель K не выбран: нужны локальная
    маршрутизация и тарифы такси.</p></div>`;
}

function renderStats(diff, demand) {
  const t = diff.totals;
  const tiers = demand.streets_by_tier;
  const kpi = [
    ["Территорий", t.territories],
    ["Исходная площадь", t.source_area_km2 + " км²"],
    ["Рабочая площадь", t.candidate_area_km2 + " км²"],
    ["Улиц Tier A / B / C", `${tiers.A} / ${tiers.B} / ${tiers.C}`],
    ["Адресов внутри", t.addresses_inside],
    ["Жилых «клиентов»", demand.residential_customers],
    ["Исключено хозпостроек", demand.excluded_outbuildings],
    ["Исключено нежилых", demand.excluded_nonresidential],
    ["Заброшено / руины", demand.excluded_abandoned_or_ruin],
  ].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join("");

  let rows = "";
  Object.keys(diff.territories).sort().forEach((key) => {
    const d = diff.territories[key];
    rows += `<tr><td>${esc(d.display_ru)}</td>
      <td class="num">${d.source_area_km2}</td>
      <td class="num">${d.candidate_area_km2}</td>
      <td class="num"><b>${d.reduction_pct}%</b></td>
      <td class="num">${d.streets_tier_a}/${d.streets_tier_b}/${d.streets_tier_c}</td>
      <td class="num">${d.addresses_inside}</td></tr>`;
  });

  document.getElementById("stats-body").innerHTML = `${kpi}
    <table>
      <thead><tr><th>Территория</th><th class="num">source км²</th>
        <th class="num">раб. км²</th><th class="num">−%</th>
        <th class="num">A/B/C</th><th class="num">адр.</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="muted small">Tier A — полный вес, Tier B — низкий вес (0.3),
    Tier C — только ручная проверка, на полигоны и тарифы не влияет.</p>`;
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
    const [source, candidate, excluded, sparse, questions, buildings, roads, diff,
           tierC, kCand, demand, zoneCand, origins] = await Promise.all([
      loadJSON("data/source-boundaries.geojson"),
      loadJSON("data/candidate-service-area.geojson"),
      loadJSON("data/excluded-large-areas.geojson"),
      loadJSON("data/sparse-building-review.geojson"),
      loadJSON("data/boundary-questions.geojson"),
      loadJSON("data/buildings.geojson"),
      loadJSON("data/roads.geojson"),
      loadJSON("data/service-area-diff.json"),
      loadJSON("data/tier-c-manual-review.geojson"),
      loadJSON("data/k-candidates.geojson"),
      loadJSON("data/demand-summary.json"),
      loadJSON("data/zone-candidates.geojson"),
      loadJSON("data/restaurant-origins.geojson"),
    ]);

    // Source OSM boundaries — dashed, reference only.
    overlays["Исходные границы OSM"] = L.geoJSON(source, {
      style: (f) => ({ color: TERRITORY_COLOR[f.properties.key] || "#6b7280",
        weight: 2, dashArray: "7 6", fill: false, opacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(sourcePopup(f.properties)),
    }).addTo(map);

    // Candidate working area — solid.
    overlays["Рабочая территория"] = L.geoJSON(candidate, {
      style: (f) => ({ color: TERRITORY_COLOR[f.properties.key] || "#2f6fed",
        weight: 3, fillColor: TERRITORY_COLOR[f.properties.key], fillOpacity: 0.18 }),
      onEachFeature: (f, l) => l.bindPopup(candidatePopup(f.properties)),
    }).addTo(map);
    addPermanentLabels(candidate);

    overlays["Исключённые поля и пустые территории"] = L.geoJSON(excluded, {
      style: (f) => ({ color: EXCLUDED_COLOR[f.properties.reason] || "#9aa0a6",
        weight: 1, fillColor: EXCLUDED_COLOR[f.properties.reason] || "#9aa0a6",
        fillOpacity: 0.22, dashArray: "3 4" }),
      onEachFeature: (f, l) => l.bindPopup(excludedPopup(f.properties)),
    });

    overlays["Редкие дома — проверить"] = L.geoJSON(sparse, {
      style: () => ({ color: "#b45309", weight: 2, fillColor: "#f59e0b", fillOpacity: 0.35 }),
      onEachFeature: (f, l) => l.bindPopup(sparsePopup(f.properties)),
    }).addTo(map);

    overlays["Спорные места (Протягайловка)"] = L.geoJSON(questions, {
      style: () => ({ color: "#d1461f", weight: 4, dashArray: "2 6" }),
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 7, color: "#d1461f", fillColor: "#fff", fillOpacity: 1, weight: 3 }),
      onEachFeature: (f, l) => l.bindPopup(questionPopup(f.properties)),
    }).addTo(map);

    overlays["Здания"] = L.geoJSON(buildings, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 1.6, weight: 0, fillOpacity: f.properties.inside_candidate ? 0.75 : 0.55,
        fillColor: f.properties.inside_candidate ? "#1d4ed8" : "#b91c1c" }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><b>${f.properties.inside_candidate
          ? "Здания внутри рабочей территории" : "Здания вне рабочей территории"}</b><br>` +
        `${esc(TERRITORY_LABEL[f.properties.territory] || f.properties.territory)}: ` +
        `${f.properties.count}</div>`),
    });

    roadFeatures = roads.features;
    overlays["Улицы"] = L.geoJSON(roads, {
      style: () => ({ color: "#6b7280", weight: 1.4, opacity: 0.8 }),
      onEachFeature: (f, l) => l.bindPopup(streetPopup(f.properties)),
    });
    overlays["Улицы без русского названия"] = L.geoJSON({
      type: "FeatureCollection",
      features: roads.features.filter((f) => f.properties.ru_status === "needs_ru_review"),
    }, {
      style: () => ({ color: "#e0451f", weight: 4, opacity: 0.95 }),
      onEachFeature: (f, l) => l.bindPopup(streetPopup(f.properties)),
    });

    // Tier C: NOT serviceable (owner decision). QA visibility only — never shapes
    // polygons, zone centres, clustering, percentiles or tariffs.
    overlays["Tier C — не обслуживается"] = L.geoJSON(tierC, {
      style: () => ({ color: "#b45309", weight: 5, dashArray: "4 5", opacity: 0.95 }),
      onEachFeature: (f, l) => l.bindPopup(tierCPopup(f.properties)),
    }).addTo(map);

    // K=4 / K=5 centres — prepared drafts, no winner chosen.
    [4, 5].forEach((k) => {
      overlays[`Центры K=${k} (черновик)`] = L.geoJSON({
        type: "FeatureCollection",
        features: kCand.features.filter((f) => f.properties.k === k),
      }, {
        pointToLayer: (f, latlng) => L.marker(latlng, {
          icon: L.divIcon({
            className: "k-centre",
            html: `<span>K${f.properties.k}·${f.properties.cluster}</span>`,
            iconSize: [0, 0],
          }),
        }),
        onEachFeature: (f, l) => l.bindPopup(kPopup(f.properties)),
      });
    });

    // Routing-based candidate zones: both K published, neither chosen.
    [4, 5].forEach((k) => {
      overlays[`Зоны K=${k} (черновик)`] = L.geoJSON({
        type: "FeatureCollection",
        features: zoneCand.features.filter((f) => f.properties.k === k),
      }, {
        style: (f) => ({ color: ZONE_COLORS[f.properties.zone % ZONE_COLORS.length],
          weight: 2, fillColor: ZONE_COLORS[f.properties.zone % ZONE_COLORS.length],
          fillOpacity: 0.25 }),
        onEachFeature: (f, l) => l.bindPopup(zonePopup(f.properties)),
      });
    });

    // Representative restaurant origins (85% central / 15% BAM + outer).
    overlays["Источники заказов (рестораны)"] = L.geoJSON(origins, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 6 + 14 * f.properties.weight, color: "#111827", weight: 2,
        fillColor: f.properties.role === "central" ? "#dc2626" : "#f59e0b",
        fillOpacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(originPopup(f.properties)),
    }).addTo(map);

    L.control.layers(null, overlays, { collapsed: false }).addTo(map);
    renderStats(diff, demand);
    setupSearch();
  } catch (err) {
    document.getElementById("stats-body").textContent = "Ошибка загрузки данных: " + err.message;
    console.error(err);
  }
}

init();
