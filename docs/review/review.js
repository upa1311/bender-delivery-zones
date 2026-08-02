/* /review/ — DESIGN tool: real route + draggable PROVISIONAL tariff boundary with
 * live price recompute. Not an approved price; nothing is published as final.
 *
 * Formula (owner-corrected; 18/6/10 rejected):
 *   base = 14 if total_km <= 3 else 14 + (total_km - 3) * 4
 *   external_surcharge = 0 if external_km <= 0 else max(5, external_km * 2)
 *   reference_price = base + external_surcharge
 * external_km = route length AFTER the (draggable) tariff boundary. */
"use strict";

const OSM_ATTR = "© OpenStreetMap contributors";
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

const basePrice = (km) => (km <= 3 ? 14 : 14 + (km - 3) * 4);
const externalSurcharge = (km) => (km <= 0 ? 0 : Math.max(5, km * 2));

async function loadJSON(p) {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json();
}

function priceCards(total, boundaryKm) {
  const externalKm = Math.max(0, total - boundaryKm);
  const base = basePrice(total);
  const sur = externalSurcharge(externalKm);
  const ref = base + sur;
  const card = (lbl, val) =>
    `<div class="price-card"><div class="lbl">${lbl}</div><div class="val">${val}</div></div>`;
  document.getElementById("price-grid").innerHTML =
    card("Всего маршрут, км", total.toFixed(3))
    + card("Обычные км (до границы)", boundaryKm.toFixed(3))
    + card("Внешние км (после границы)", externalKm.toFixed(3))
    + card("base, руб.", base.toFixed(2))
    + card("внешняя надбавка, руб.", sur.toFixed(2))
    + card("расчётный итог, руб.", ref.toFixed(2));
  return { externalKm, base, sur, ref };
}

function renderZones(sum) {
  const z = sum.zone_stats;
  const colors = ["#2a9d3f", "#f2c500", "#f07f14", "#d62828", "#8338ec", "#0e7490"];
  let rows = "";
  Object.keys(z).sort((a, b) => a - b).forEach((zid, i) => {
    const s = z[zid];
    rows += `<tr><td><span class="zsw" style="background:${colors[i % colors.length]}"></span>Зона ${zid}</td>`
      + `<td class="num">${s.n}</td><td class="num">${s.price_min}–${s.price_max}</td>`
      + `<td class="num">${s.km_min}–${s.km_max}</td></tr>`;
  });
  const gvf = sum.zone_candidates_gvf;
  const gvfRows = Object.keys(gvf).sort((a, b) => a - b)
    .map((k) => `${k} зон: GVF ${gvf[k].gvf}`).join(" · ");
  document.getElementById("zones-body").innerHTML =
    `<p class="small">Рекомендовано <b>${sum.recommended_zone_count}</b> зон`
    + ` (границы цены, руб.: ${sum.recommended_breaks_price.join(", ")}). ${gvfRows}.</p>`
    + `<table class="zones"><thead><tr><th>внутренняя зона</th><th class="num">адресов</th>`
    + `<th class="num">цена руб. (min–max)</th><th class="num">route_km (min–max)</th></tr></thead>`
    + `<tbody>${rows}</tbody></table>`
    + `<p class="small warn">Внешние территории (${sum.external_addresses_pending} адр.) `
    + `получат зону после утверждения границы и построения их маршрутов.</p>`;
}

async function init() {
  const map = L.map("route-map");
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: OSM_ATTR }).addTo(map);

  let data;
  try { data = await loadJSON("data/parkany-route-boundary.json"); }
  catch (e) { document.getElementById("route-map").innerHTML = "Ошибка загрузки маршрута: " + esc(e.message); return; }

  const coords = data.route_lonlat;          // [lon,lat]
  const cum = data.route_cum_km;             // km from origin per vertex
  const total = data.osrm_total_km;
  const latlngs = coords.map((c) => [c[1], c[0]]);

  L.polyline(latlngs, { color: "#1f4e79", weight: 5, opacity: 0.9 }).addTo(map);
  map.fitBounds(L.latLngBounds(latlngs), { padding: [30, 30] });

  L.circleMarker([data.origin.lat, data.origin.lon],
    { radius: 7, color: "#111827", fillColor: "#dc2626", fillOpacity: 1, weight: 2 })
    .addTo(map).bindPopup(`<b>Отправление</b><br>${esc(data.origin.label)}`);
  L.circleMarker([data.destination.lat, data.destination.lon],
    { radius: 7, color: "#111827", fillColor: "#2563eb", fillOpacity: 1, weight: 2 })
    .addTo(map).bindPopup(`<b>${esc(data.destination.address)}</b><br>OSRM ${total} км · Яндекс контроль ${data.yandex_control_km} км`);

  // Candidate crossings (data-derived, not authoritative office addresses).
  data.boundary_candidates.filter((c) => c.crosses).forEach((c) => {
    L.circleMarker([c.exit_lonlat[1], c.exit_lonlat[0]],
      { radius: 6, color: "#1d4ed8", fillColor: "#93c5fd", fillOpacity: 0.9, weight: 2 })
      .addTo(map).bindPopup(
        `<b>Кандидат границы (OSM r${esc(c.relation_id)})</b><br>`
        + `${c.km_from_origin} км от отправления · внешних ${c.external_km_beyond} км`);
  });

  // Nearest route-vertex helper for snapping the draggable boundary to the route.
  const nearestIdx = (lat, lng) => {
    let best = 0, bd = Infinity;
    for (let i = 0; i < latlngs.length; i++) {
      const d = (latlngs[i][0] - lat) ** 2 + (latlngs[i][1] - lng) ** 2;
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  };

  // Initial provisional boundary index.
  let bIdx = cum.findIndex((v) => v >= data.provisional_boundary_km_from_origin);
  if (bIdx < 0) bIdx = Math.floor(latlngs.length * 0.5);

  const boundary = L.marker(latlngs[bIdx], {
    draggable: true,
    icon: L.divIcon({ className: "", iconSize: [18, 18],
      html: '<div style="width:16px;height:16px;border-radius:50%;background:#dc2626;'
        + 'border:3px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5)"></div>' }),
  }).addTo(map).bindTooltip("Тарифная граница (PROVISIONAL) — тяните",
    { permanent: false });

  let approved = false;
  const recompute = () => {
    const boundaryKm = cum[bIdx];
    const r = priceCards(total, boundaryKm);
    if (!approved) {
      document.getElementById("approve-note").textContent =
        `PROVISIONAL: граница на ${boundaryKm.toFixed(3)} км, внешних ${r.externalKm.toFixed(3)} км.`;
    }
  };
  boundary.on("drag", (e) => {
    const p = e.target.getLatLng();
    bIdx = nearestIdx(p.lat, p.lng);
    boundary.setLatLng(latlngs[bIdx]);   // snap to the route
    recompute();
  });
  recompute();

  document.getElementById("approve").addEventListener("click", () => {
    approved = true;
    const boundaryKm = cum[bIdx];
    const externalKm = Math.max(0, total - boundaryKm);
    document.getElementById("approve-note").innerHTML =
      `<span class="warn">Выбор зафиксирован в интерфейсе (DESIGN): граница `
      + `${boundaryKm.toFixed(3)} км от отправления, внешних ${externalKm.toFixed(3)} км, `
      + `итог ${(basePrice(total) + externalSurcharge(externalKm)).toFixed(2)} руб.</span> `
      + `Это НЕ публикация: координата не сохраняется как окончательная тарифная граница `
      + `и не уходит в production до подтверждения владельцем.`;
  });

  // Zones + Кишинёвская + K4 comparison
  try {
    const sum = await loadJSON("data/reference-tariff-summary.json");
    renderZones(sum);
    const k = sum.kishinevskaya;
    document.getElementById("kish").innerHTML =
      `route_km в данных: <b>${k.data_route_km_values.join(", ")}</b> км; ожидаемое по `
      + `Яндексу: <b>${esc(k.yandex_expected_km)}</b> км. <span class="warn">route_km завышен</span> — `
      + `Яндекс недоступен в этой среде, требуется независимая сверка (влияет на base_price).`;
    document.getElementById("k4cmp").innerHTML =
      `Старая модель — 4 зоны K4 по километровым полосам. Новая — `
      + `<b>${sum.recommended_zone_count}</b> внутренних зон по фактическому разбросу цены `
      + `(Jenks), диапазоны в таблице выше. Старые 4 зоны K4 не сохранены автоматически и `
      + `не заменены как финал; сравнение по адресам — в reference-tariff-v2.csv `
      + `(колонка old_k4_zone_id).`;
  } catch (e) {
    document.getElementById("zones-body").textContent = "Ошибка загрузки зон: " + esc(e.message);
  }
}

init();
