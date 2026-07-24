/* Final catalog page: table + colour-by-zone map. The permanent zone colours
 * are identical to the polygons, points, legend and cards. No prices shown. */
"use strict";

const ZC = { 1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828" };
const STATUS_COLOR = { disputed: "#7c3aed", no_delivery: "#9ca3af", excluded: "#6b7280" };
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";
const MAX_ROWS = 800; // table render cap; filters/search narrow below it

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

function colorOf(p) {
  if (p.zone_id && ZC[p.zone_id]) return ZC[p.zone_id];
  return STATUS_COLOR[p.service_status] || "#6b7280";
}

const map = L.map("cat-map", { preferCanvas: true }).setView([46.83, 29.48], 12);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);

let all = [];         // address rows (from points geojson)
let markerIndex = new Map(); // uid -> layer
let highlight = null;
let sortKey = "settlement_ru", sortDir = 1;

const hnKey = (h) => {
  const t = (h || "").trim();
  const m = t.match(/^\d+/);
  return [m ? parseInt(m[0], 10) : 1e9, t];
};

async function loadJSON(p) { const r = await fetch(p); if (!r.ok) throw new Error(p + " " + r.status); return r.json(); }

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

function currentFilter() {
  const qs = document.getElementById("q-street").value.trim().toLowerCase();
  const qh = document.getElementById("q-house").value.trim().toLowerCase();
  const st = document.getElementById("f-settlement").value;
  const di = document.getElementById("f-district").value;
  const zones = new Set([...document.querySelectorAll(".fz:checked")].map((c) => +c.value));
  const nod = document.getElementById("f-nodelivery").checked;
  const dis = document.getElementById("f-disputed").checked;
  return (r) => {
    if (qs && !(r.street_ru || "").toLowerCase().includes(qs)) return false;
    if (qh && !(r.housenumber || "").toLowerCase().includes(qh)) return false;
    if (st && r.settlement_ru !== st) return false;
    if (di && r.district_ru !== di) return false;
    if (r.service_status === "disputed") return dis;
    if (r.service_status === "no_delivery") return nod;
    if (r.service_status === "excluded") return false;
    return r.zone_id ? zones.has(r.zone_id) : false;
  };
}

function render() {
  const pred = currentFilter();
  const rows = all.filter(pred);
  rows.sort((a, b) => {
    let x = a[sortKey], y = b[sortKey];
    if (sortKey === "housenumber") { const ka = hnKey(x), kb = hnKey(y);
      return sortDir * (ka[0] - kb[0] || ka[1].localeCompare(kb[1])); }
    if (sortKey === "zone_id" || sortKey === "expected_km") return sortDir * ((x || 0) - (y || 0));
    return sortDir * String(x || "").localeCompare(String(y || ""));
  });
  const body = document.getElementById("cat-body");
  body.innerHTML = rows.slice(0, MAX_ROWS).map((r) => {
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
    `${rows.length} объектов${rows.length > MAX_ROWS ? ` (показаны первые ${MAX_ROWS})` : ""}`;
}

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
  highlight = L.circleMarker([r.lat, r.lon], { radius: 11, color: "#111827",
    weight: 3, fillColor: colorOf(r), fillOpacity: 0.9 }).addTo(map);
  houseCard(r);
}

async function init() {
  try {
    const [polys, points] = await Promise.all([
      loadJSON("data/final-zone-polygons.geojson"),
      loadJSON("data/final-address-zone-points.geojson"),
    ]);
    // zone polygons — translucent fill, visible borders, permanent colours
    L.geoJSON(polys, {
      style: (f) => ({ color: "#1f2937", weight: 2,
        fillColor: f.properties.color, fillOpacity: 0.28 }),
      onEachFeature: (f, l) => l.bindPopup(
        `<b>${f.properties.zone_name}</b><br>${esc(f.properties.component)}`
        + (f.properties.note ? `<br><span class="muted small">${esc(f.properties.note)}</span>` : "")),
    }).addTo(map);

    all = points.features.map((f) => ({ ...f.properties,
      lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }));

    // house points coloured by zone (canvas renderer for ~23k points)
    const layer = L.geoJSON(points, {
      pointToLayer: (f, ll) => {
        const m = L.circleMarker(ll, { radius: 3, weight: 0,
          fillColor: colorOf(f.properties), fillOpacity: 0.8 });
        markerIndex.set(f.properties.uid, m);
        return m;
      },
      onEachFeature: (f, l) => l.on("click", () => focusUid(f.properties.uid)),
    }).addTo(map);
    try { map.fitBounds(layer.getBounds(), { padding: [20, 20] }); } catch (e) { /* empty */ }

    buildFilters();
    render();
    ["q-street", "q-house", "f-settlement", "f-district", "f-nodelivery", "f-disputed"]
      .forEach((id) => document.getElementById(id).addEventListener("input", () => {
        if (id === "f-settlement") refreshDistricts();
        render();
      }));
    document.querySelectorAll(".fz").forEach((c) =>
      c.addEventListener("change", render));
    document.querySelectorAll("#cat-table thead th").forEach((th) =>
      th.addEventListener("click", () => {
        const k = th.dataset.sort;
        sortDir = (sortKey === k) ? -sortDir : 1; sortKey = k; render();
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
