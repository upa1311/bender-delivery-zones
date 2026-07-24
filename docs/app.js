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

const SETTLEMENT_OF = {
  bender_core: "Бендеры", bender_lipcani: "Бендеры, Липканы",
  giska: "Гиска", parkany: "Парканы", protyagailovka: "Протягайловка",
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
      <tr><td class="k">населённый пункт</td><td>${esc(SETTLEMENT_OF[p.settlement] || "—")}</td></tr>
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

function originPopup(p) {
  return `<div class="popup">
    <div class="popup-title">${esc(p.key)}</div>
    <table>
      <tr><td class="k">роль</td><td>${esc(p.role)}</td></tr>
      <tr><td class="k">доля заказов</td><td>${p.weight}</td></tr>
      <tr><td class="k">заведений в кластере</td><td>${p.poi_count}</td></tr>
      ${p.distance_to_bam_landmark_km != null
        ? `<tr><td class="k">до ориентира БАМ</td><td>${p.distance_to_bam_landmark_km} км</td></tr>` : ""}
    </table>
    <p class="muted small">Представительный источник заказов (кластер заведений),
    не один POI.</p></div>`;
}

function bandPopup(p, metrics, k) {
  const res = metrics.candidates[String(k)];
  const z = res ? res.zones.find((x) => x.zone === p.zone) : null;
  const km = z ? z.km : null;
  return `<div class="popup">
    <div class="popup-title">${esc(p.name)} — K=${p.k}
      <span class="badge review">тариф не назначен</span></div>
    <table>
      ${km ? `<tr><td class="k">диапазон км</td><td>${km.min} – ${km.max}</td></tr>
      <tr><td class="k">p50 / p90 км</td><td>${km.p50} / ${km.p90}</td></tr>
      <tr><td class="k">p50 мин</td><td>${z.minutes.p50}</td></tr>
      <tr><td class="k">единиц доставки</td><td>${z.unique_delivery_units}</td></tr>
      <tr><td class="k">из них адресных</td><td>${z.address_units}</td></tr>
      <tr><td class="k">вес спроса</td><td>${z.demand_weight}</td></tr>
      <tr><td class="k">центр / БАМ км</td><td>${z.central_km_p50} / ${z.bam_km_p50}</td></tr>` : ""}
      <tr><td class="k">площадь</td><td>${p.area_km2} км²</td></tr>
    </table>
    <p class="muted small">Зоны — упорядоченные диапазоны стоимости по дорожным
    километрам OSRM, а не географические кластеры. Деньги не назначены.</p></div>`;
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
    // Same-named streets in different settlements are DIFFERENT streets: list
    // each place separately so they cannot be confused.
    const places = new Map();
    matches.forEach((f) => {
      const p = f.properties;
      const place = p.settlement_ru || SETTLEMENT_OF[p.settlement] || "—";
      const key = `${p.ru_display || p.name}||${place}`;
      places.set(key, (places.get(key) || 0) + 1);
    });
    const variants = [...places.entries()].sort()
      .map(([key, n]) => {
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

async function init() {
  try {
    const [source, candidate, excluded, sparse, questions, buildings, roads, diff,
           tierC, demand, bands, origins, bandMetrics, exceptions, unitPoints, noAddress, severnyRoutes, severnyArea, varnitaAdmin, varnitaVillage, severnyUnits] = await Promise.all([
      loadJSON("data/source-boundaries.geojson"),
      loadJSON("data/candidate-service-area.geojson"),
      loadJSON("data/excluded-large-areas.geojson"),
      loadJSON("data/sparse-building-review.geojson"),
      loadJSON("data/boundary-questions.geojson"),
      loadJSON("data/buildings.geojson"),
      loadJSON("data/roads.geojson"),
      loadJSON("data/service-area-diff.json"),
      loadJSON("data/tier-c-manual-review.geojson"),
      loadJSON("data/demand-summary.json"),
      loadJSON("data/tariff-bands.geojson"),
      loadJSON("data/restaurant-origins.geojson"),
      loadJSON("data/tariff-band-metrics.json"),
      loadJSON("data/delivery-exceptions.geojson"),
      loadJSON("data/delivery-unit-points.geojson"),
      loadJSON("data/no-address-data.geojson"),
      loadJSON("data/severny-route-qa.geojson"),
      loadJSON("data/severny-service-area.geojson"),
      loadJSON("data/varnita-admin-reference.geojson"),
      loadJSON("data/varnita-village-no-delivery.geojson"),
      loadJSON("data/severny-delivery-units.geojson"),
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

    // Ordered TARIFF BANDS (Zone 1 = cheapest routes ... Zone N = farthest).
    // Mutually exclusive by construction; both K published, neither chosen.
    const BAND_COLORS = ["#1a9850", "#a6d96a", "#fdae61", "#f46d43", "#d73027"];
    [4, 5].forEach((k) => {
      const feats = bands.features.filter((f) => f.properties.k === k);
      const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, {
        style: (f) => ({
          color: BAND_COLORS[(f.properties.zone - 1) % BAND_COLORS.length],
          weight: 1.5,
          fillColor: BAND_COLORS[(f.properties.zone - 1) % BAND_COLORS.length],
          fillOpacity: 0.45 }),
        onEachFeature: (f, l) => l.bindPopup(bandPopup(f.properties, bandMetrics, k)),
      });
      overlays[`Тарифные зоны K=${k} (Zone 1…${k})`] = layer;
      if (k === 4) layer.addTo(map);
    });

    // Address/unit points coloured by band — the CSV remains the source of truth.
    [4, 5].forEach((k) => {
      const feats = unitPoints.features.filter((f) => f.properties.k === k);
      overlays[`Адреса по зонам K=${k}`] = L.geoJSON(
        { type: "FeatureCollection", features: feats }, {
          pointToLayer: (f, latlng) => L.circleMarker(latlng, {
            radius: 2, weight: 0, fillOpacity: 0.9,
            fillColor: BAND_COLORS[(f.properties.zone - 1) % BAND_COLORS.length] }),
          onEachFeature: (f, l) => l.bindPopup(
            `<div class="popup"><b>${esc(f.properties.name)}</b> — K=${f.properties.k}<br>`
            + `единиц доставки: ${f.properties.units}</div>`),
        });
    });

    // Service area with no assigned address data — shown, never silently coloured.
    overlays["Нет адресных данных"] = L.geoJSON(noAddress, {
      style: () => ({ color: "#6b7280", weight: 1, fillColor: "#9ca3af",
        fillOpacity: 0.35, dashArray: "2 3" }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><b>Нет адресных данных</b><br>${esc(f.properties.note)}<br>`
        + `площадь: ${(f.properties.area_m2 / 10000).toFixed(2)} га</div>`),
    });

    // Representative restaurant origins (85% central / 15% BAM + other outer).
    overlays["Источники заказов (рестораны)"] = L.geoJSON(origins, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 6 + 14 * f.properties.weight, color: "#111827", weight: 2,
        fillColor: f.properties.role === "central" ? "#dc2626"
          : (f.properties.role === "bam" ? "#f59e0b" : "#fcd34d"),
        fillOpacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(originPopup(f.properties)),
    }).addTo(map);

    // Explicit exception list (never silently dropped).
    overlays["Исключения (не в зонах)"] = L.geoJSON(exceptions, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 4, color: "#7f1d1d", weight: 1, fillColor: "#ef4444",
        fillOpacity: 0.85 }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><b>Исключение</b><br>${esc(f.properties.uid)}<br>` +
        `<code>${esc(f.properties.reason)}</code></div>`),
    });

    // Северный: маршруты (QA) + неподтверждённый кандидат-маркер.
    overlays["Северный — маршруты (QA)"] = L.geoJSON(severnyRoutes, {
      style: () => ({ color: "#0ea5e9", weight: 3, opacity: 0.85, dashArray: "5 4" }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><b>Маршрут «Северный»</b><br>${esc(f.properties.name)}</div>`),
    });
    overlays["Северный — жилой контур (кандидат)"] = L.geoJSON(severnyArea, {
      style: () => ({ color: "#0e9488", weight: 2, fillColor: "#0e9488",
        fillOpacity: 0.35 }),
      onEachFeature: (f, l) => { const p = f.properties; l.bindPopup(
        `<div class="popup"><div class="popup-title">${esc(p.district_label_ru)} `
        + `<span class="badge review">owner review</span></div><table>`
        + `<tr><td class="k">населённый пункт</td><td>${esc(p.settlement_ru)}</td></tr>`
        + `<tr><td class="k">район</td><td>${esc(p.district_ru)}</td></tr>`
        + `<tr><td class="k">зданий включено</td><td>${p.final_included_buildings}</td></tr>`
        + `<tr><td class="k">адресов OSM</td><td>${p.confirmed_address_count}</td></tr>`
        + `<tr><td class="k">квартирных</td><td>${p.apartment_building_count}</td></tr>`
        + `<tr><td class="k">севернее Варницы</td><td>${p.north_of_varnita_village ? "да" : "нет"}</td></tr>`
        + `</table>`
        + `<p class="muted small">Нумерация 1–105 не подтверждена для импорта</p>`
        + `<p class="muted small">${esc(p.note)}</p></div>`); },
    });
    // Varnița: the admin claim is a REFERENCE LINE (it encloses the Bender
    // Северный enclave, so it must never be filled); only the village built-up
    // area carries the grey no-delivery meaning.
    overlays["Варница — админ-граница (справочно)"] = L.geoJSON(varnitaAdmin, {
      style: () => ({ color: "#6b7280", weight: 2, dashArray: "8 6", fill: false,
        opacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><div class="popup-title">Варница — админ-граница</div>`
        + `<p class="muted small">${esc(f.properties.note)}</p></div>`),
    });
    overlays["Варница (село) — без доставки"] = L.geoJSON(varnitaVillage, {
      style: () => ({ color: "#4b5563", weight: 1.5, fillColor: "#9ca3af",
        fillOpacity: 0.55 }),
      onEachFeature: (f, l) => l.bindPopup(
        `<div class="popup"><div class="popup-title">Варница (село) `
        + `<span class="badge missing">${esc(f.properties.service_status)}</span></div>`
        + `<p class="muted small">${esc(f.properties.note)}</p></div>`),
    });

    // Северный delivery units coloured by assigned zone.
    overlays["Северный — адреса по зонам"] = L.geoJSON(severnyUnits, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 4, weight: 1, color: "#111827",
        fillColor: BAND_COLORS[(f.properties.assigned_zone - 1) % BAND_COLORS.length],
        fillOpacity: 0.9 }),
      onEachFeature: (f, l) => { const p = f.properties; l.bindPopup(
        `<div class="popup"><div class="popup-title">Zone ${p.assigned_zone}</div><table>`
        + `<tr><td class="k">адрес</td><td>${p.addressed ? esc(p.street_ru + " " + p.housenumber) : "без адреса"}</td></tr>`
        + `<tr><td class="k">центр</td><td>${p.central_km} км / ${p.central_min} мин</td></tr>`
        + `<tr><td class="k">БАМ</td><td>${p.bam_km} км / ${p.bam_min} мин</td></tr>`
        + `<tr><td class="k">ожидаемое</td><td>${p.expected_km} км</td></tr>`
        + `<tr><td class="k">транзит Варница</td><td>${p.route_through_varnita_village ? "да" : "нет"}</td></tr>`
        + `</table></div>`); },
    });

    L.control.layers(null, overlays, { collapsed: false }).addTo(map);
    renderStats(diff, demand);
    setupSearch();
  } catch (err) {
    document.getElementById("stats-body").textContent = "Ошибка загрузки данных: " + err.message;
    console.error(err);
  }
}

init();
