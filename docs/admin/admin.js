/* Static GitHub Pages V1 admin console. OSRM errors are always explicit. */
"use strict";

const OSRM_ENDPOINT = "https://router.project-osrm.org/route/v1/driving";
const ZONE_COLORS = { 1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828" };
const { basePrice, externalSurcharge, symmetricRouteGateMetrics } =
  globalThis.BenderTariffModel;

let MAP, POINT_LAYER, ROUTE_LAYER, A_MARKER, B_MARKER;
let CATALOG = [], FILTERED = [], GATE = null, INTERNAL_ORIGIN = null;
let SELECTED_A = null, SELECTED_B = null, LAST_ROUTE = null;

const esc = (value) => String(value ?? "").replace(/[&<>\"]/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character]));

async function loadJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function parseAddress(row) {
  const parts = row[1].split(",").map((part) => part.trim());
  return {
    uid: row[0], address: row[1], lon: row[2], lat: row[3], status: row[4],
    catalogRouteKm: row[5], oldZone: row[6], zone: row[7], catalogPrice: row[8],
    district: parts[0] || "", street: parts.slice(1, -1).join(", "),
    house: parts.at(-1) || "",
  };
}

function zoneBadge(item) {
  const color = ZONE_COLORS[item.zone] || "#94a3b8";
  return `<span class="zone-dot" style="background:${color}"></span>зона ${esc(item.zone || "—")}`;
}

function renderPointLayer(items) {
  if (POINT_LAYER) MAP.removeLayer(POINT_LAYER);
  const markers = items.filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon))
    .map((item) => L.circleMarker([item.lat, item.lon], {
      renderer: MAP.options.renderer,
      radius: 2.2,
      weight: 0,
      fillColor: ZONE_COLORS[item.zone] || "#94a3b8",
      fillOpacity: item.status === "routed" ? 0.8 : 0.35,
    }));
  POINT_LAYER = L.layerGroup(markers).addTo(MAP);
}

function filters() {
  return {
    street: document.getElementById("street-filter").value.trim().toLocaleLowerCase("ru"),
    house: document.getElementById("house-filter").value.trim().toLocaleLowerCase("ru"),
    district: document.getElementById("district-filter").value,
    zone: document.getElementById("zone-filter").value,
  };
}

function applyFilters() {
  const query = filters();
  FILTERED = CATALOG.filter((item) => (
    (!query.street || item.street.toLocaleLowerCase("ru").includes(query.street))
    && (!query.house || item.house.toLocaleLowerCase("ru").includes(query.house))
    && (!query.district || item.district === query.district)
    && (!query.zone || String(item.zone) === query.zone)
  ));
  document.getElementById("filter-count").innerHTML =
    `Найдено <b>${FILTERED.length.toLocaleString("ru-RU")}</b> из 9 216`;
  document.getElementById("address-results").innerHTML = FILTERED.slice(0, 80).map((item) => (
    `<button class="address-result" type="button" data-uid="${esc(item.uid)}">`
    + `${esc(item.address)}<small>${zoneBadge(item)} · UID ${esc(item.uid)}</small></button>`
  )).join("") || '<span class="small muted">Совпадений нет.</span>';
  document.querySelectorAll(".address-result").forEach((button) => button.addEventListener(
    "click", () => selectAddress(button.dataset.uid),
  ));
  renderPointLayer(FILTERED);
}

function selectedTarget() {
  return document.querySelector('input[name="target"]:checked').value;
}

function selectedCard(item, label) {
  if (!item) return `<b>${label}</b><span>не выбран</span>`;
  return `<b>${label}</b><span>${esc(item.address)}</span><small>${zoneBadge(item)} · ${esc(item.uid)}</small>`;
}

function renderSelected() {
  document.getElementById("selected-a").innerHTML = selectedCard(SELECTED_A, "A");
  document.getElementById("selected-b").innerHTML = selectedCard(SELECTED_B, "B");
  if (A_MARKER) MAP.removeLayer(A_MARKER);
  if (B_MARKER) MAP.removeLayer(B_MARKER);
  if (SELECTED_A) A_MARKER = L.marker([SELECTED_A.lat, SELECTED_A.lon]).bindTooltip("A").addTo(MAP);
  if (SELECTED_B) B_MARKER = L.marker([SELECTED_B.lat, SELECTED_B.lon]).bindTooltip("B").addTo(MAP);
}

function selectAddress(uid) {
  const item = CATALOG.find((candidate) => candidate.uid === uid);
  if (!item) return;
  if (selectedTarget() === "a") {
    SELECTED_A = item;
    document.getElementById("target-b").checked = true;
  } else {
    SELECTED_B = item;
  }
  LAST_ROUTE = null;
  document.getElementById("calculation").hidden = true;
  document.getElementById("route-error").textContent = "";
  renderSelected();
}

function renderRoute(route) {
  if (ROUTE_LAYER) MAP.removeLayer(ROUTE_LAYER);
  ROUTE_LAYER = L.polyline(route.coordinates.map((point) => [point[1], point[0]]), {
    color: "#2563eb", weight: 5, opacity: 0.9,
  }).addTo(MAP);
  MAP.fitBounds(ROUTE_LAYER.getBounds(), { padding: [28, 28] });
}

function renderCalculation(route) {
  const metrics = symmetricRouteGateMetrics(
    route.coordinates, route.km, GATE.geometry.coordinates, INTERNAL_ORIGIN,
  );
  const base = basePrice(route.km);
  const surcharge = externalSurcharge(metrics.externalKm);
  const total = base + surcharge;
  const output = document.getElementById("calculation");
  output.hidden = false;
  output.dataset.total = total.toFixed(6);
  output.dataset.externalKm = metrics.externalKm.toFixed(6);
  output.dataset.crosses = String(metrics.crosses);
  document.getElementById("route-km").textContent = `${route.km.toFixed(3)} км`;
  document.getElementById("route-minutes").textContent = `${route.minutes.toFixed(1)} мин`;
  document.getElementById("route-zones").textContent = `${SELECTED_A.zone} / ${SELECTED_B.zone}`;
  document.getElementById("route-crosses").textContent = metrics.crosses ? "пересекает" : "не пересекает";
  document.getElementById("route-external").textContent = `${metrics.externalKm.toFixed(3)} км`;
  document.getElementById("route-base").textContent = `${base.toFixed(2)} ₽`;
  document.getElementById("route-surcharge").textContent = `${surcharge.toFixed(2)} ₽`;
  document.getElementById("route-total").textContent = `${total.toFixed(2)} ₽`;
  return { metrics, base, surcharge, total };
}

async function calculateRoute() {
  const error = document.getElementById("route-error");
  const button = document.getElementById("calculate-route");
  error.textContent = "";
  document.getElementById("calculation").hidden = true;
  if (!SELECTED_A || !SELECTED_B) { error.textContent = "Выберите точные адреса A и B."; return; }
  if (SELECTED_A.uid === SELECTED_B.uid) { error.textContent = "Адреса A и B должны различаться."; return; }
  if (SELECTED_A.status !== "routed" || SELECTED_B.status !== "routed") {
    error.textContent = "Для одного из адресов нет утверждённой маршрутной записи.";
    return;
  }
  button.disabled = true;
  button.textContent = "Запрос OSRM…";
  try {
    const coordinates = `${SELECTED_A.lon},${SELECTED_A.lat};${SELECTED_B.lon},${SELECTED_B.lat}`;
    const response = await fetch(
      `${OSRM_ENDPOINT}/${coordinates}?overview=full&geometries=geojson&steps=false`,
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (payload.code !== "Ok" || !payload.routes?.length) {
      throw new Error(payload.message || payload.code || "маршрут отсутствует");
    }
    const osrmRoute = payload.routes[0];
    if (!osrmRoute.geometry?.coordinates?.length || !Number.isFinite(osrmRoute.distance)
      || !Number.isFinite(osrmRoute.duration)) throw new Error("неполный ответ маршрутизатора");
    LAST_ROUTE = {
      coordinates: osrmRoute.geometry.coordinates,
      km: osrmRoute.distance / 1000,
      minutes: osrmRoute.duration / 60,
    };
    renderRoute(LAST_ROUTE);
    renderCalculation(LAST_ROUTE);
  } catch (routeError) {
    LAST_ROUTE = null;
    if (ROUTE_LAYER) { MAP.removeLayer(ROUTE_LAYER); ROUTE_LAYER = null; }
    error.textContent = `OSRM недоступен: ${routeError.message}. Расчёт не выполнен.`;
  } finally {
    button.disabled = false;
    button.textContent = "Построить A → B";
  }
}

function swapAddresses() {
  if (!SELECTED_A || !SELECTED_B) {
    document.getElementById("route-error").textContent = "Сначала выберите адреса A и B.";
    return;
  }
  [SELECTED_A, SELECTED_B] = [SELECTED_B, SELECTED_A];
  renderSelected();
  if (LAST_ROUTE) {
    LAST_ROUTE = { ...LAST_ROUTE, coordinates: [...LAST_ROUTE.coordinates].reverse() };
    renderRoute(LAST_ROUTE);
    renderCalculation(LAST_ROUTE);
  }
}

async function init() {
  MAP = L.map("admin-map", { preferCanvas: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "© OpenStreetMap contributors",
  }).addTo(MAP);
  try {
    const [index, parkany, summary] = await Promise.all([
      loadJSON("../review/data/address-index.json"),
      loadJSON("../review/data/parkany-route-boundary.json"),
      loadJSON("../review/data/reference-tariff-v3-summary.json"),
    ]);
    CATALOG = index.addresses.map(parseAddress);
    GATE = parkany.approved_gate;
    INTERNAL_ORIGIN = [summary.origin.lon, summary.origin.lat];
    if (CATALOG.length !== 9216 || summary.catalog_total !== 9216
      || summary.status_counts.routed !== 9215 || summary.status_counts.duplicate !== 1) {
      throw new Error("нарушена целостность опубликованного реестра");
    }
    const districts = [...new Set(CATALOG.map((item) => item.district))].sort();
    document.getElementById("district-filter").insertAdjacentHTML(
      "beforeend", districts.map((district) => `<option>${esc(district)}</option>`).join(""),
    );
    document.getElementById("model-status").innerHTML =
      `<b>9 216</b> записей · routed <b>9 215</b> · duplicate <b>1</b><br>`
      + `<span class="gate-swatch"></span>${esc(GATE.status)} · `
      + `${GATE.center_lonlat[1].toFixed(6)}, ${GATE.center_lonlat[0].toFixed(6)} · `
      + `route index ${GATE.corridor_route_index}<br>`
      + `Jenks: ${summary.recommended_breaks_price.join(" / ")} · `
      + `gate ${summary.routes_crossing_gate} / ${summary.routes_not_crossing_gate}`;
    const allCoordinates = CATALOG.filter((item) => Number.isFinite(item.lat));
    MAP.fitBounds(allCoordinates.map((item) => [item.lat, item.lon]), { padding: [18, 18] });
    L.polyline(GATE.geometry.coordinates.map((point) => [point[1], point[0]]), {
      color: "#dc2626", weight: 5,
    }).bindTooltip("owner_approved gate").addTo(MAP);
    L.circleMarker([GATE.center_lonlat[1], GATE.center_lonlat[0]], {
      radius: 6, color: "#991b1b", fillColor: "#dc2626", fillOpacity: 1,
    }).addTo(MAP);
    applyFilters();
  } catch (error) {
    document.getElementById("model-status").innerHTML = `<span class="warn">Ошибка: ${esc(error.message)}</span>`;
    return;
  }
  let filterTimer;
  for (const id of ["street-filter", "house-filter", "district-filter", "zone-filter"]) {
    document.getElementById(id).addEventListener("input", () => {
      clearTimeout(filterTimer);
      filterTimer = setTimeout(applyFilters, 80);
    });
  }
  document.getElementById("calculate-route").addEventListener("click", calculateRoute);
  document.getElementById("swap-addresses").addEventListener("click", swapAddresses);
  window.__adminTest = {
    snapshot: () => ({
      catalogCount: CATALOG.length, filteredCount: FILTERED.length,
      a: SELECTED_A?.uid || null, b: SELECTED_B?.uid || null,
      route: LAST_ROUTE ? { km: LAST_ROUTE.km, minutes: LAST_ROUTE.minutes,
        total: Number(document.getElementById("calculation").dataset.total) } : null,
    }),
  };
  document.documentElement.dataset.adminReady = "true";
}

init();
