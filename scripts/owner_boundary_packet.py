"""Owner boundary decision packet — ANALYSIS layer only.

Builds the owner-facing artifacts for the external-tariff boundary decision:
a boundary-candidate comparison (with real OSM metadata fetched reproducibly from
the OSM API), a self-contained owner map (SVG + HTML layer toggles), the boundary
scenario impact for the 12 available routes, and the decision document. Nothing is
applied to production; no boundary is set VERIFIED_FOR_TARIFF and no owner approval
is granted by this script.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "outside_city_distance", ROOT / "scripts/outside_city_distance.py")
OC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OC)

BOUNDARIES = ROOT / "docs/data/source-boundaries.geojson"
SETTLEMENTS = ROOT / "docs/data/settlements.geojson"
FEES_CSV = ROOT / "data/interim/outside-city-distance-v1.csv"
SCEN_CSV = ROOT / "data/interim/outside-city-boundary-scenarios-v1.csv"
COMPARE_CSV = ROOT / "data/interim/boundary-candidates-comparison-v1.csv"
MAP_HTML = ROOT / "reports/zone-model-audit/owner-boundary-map-v1.html"
MAP_SVG = ROOT / "reports/zone-model-audit/owner-boundary-map-v1.svg"
MAP_PNG = ROOT / "reports/zone-model-audit/owner-boundary-map-v1.png"
DECISION_MD = ROOT / "reports/zone-model-audit/OWNER_BOUNDARY_DECISION.md"
PROVIDER_MD = ROOT / "reports/zone-model-audit/route-provider-investigation-v1.md"
PILOT_MD = ROOT / "reports/zone-model-audit/route-generation-pilot-v1.md"

# Real OSM metadata, fetched from the OSM API on 2026-07-31 (reproducible via the
# recorded URLs). License: ODbL. Recorded here as provenance, not invented.
OSM_RELATIONS = {
    "12463379": {"name": "Бендеры", "admin_level": "8", "place": "city",
                 "type": "boundary", "boundary": "administrative", "version": "19",
                 "timestamp": "2026-07-31T19:59:13Z", "changeset": "186727422",
                 "geometry_in_repo": "yes (source-boundaries.geojson key=bender)",
                 "area_km2": 21.048},
    "9581354": {"name": "Municipiul Bender", "admin_level": "4",
                "place": "municipality", "type": "boundary",
                "boundary": "administrative", "version": "36",
                "timestamp": "2025-09-07T14:00:47Z", "changeset": "171586193",
                "geometry_in_repo": "no (metadata only)", "area_km2": ""},
    "944727": {"name": "Бендеры", "admin_level": "5", "place": "municipality",
               "type": "boundary", "boundary": "administrative", "version": "72",
               "timestamp": "2026-07-31T19:57:37Z", "changeset": "186727328",
               "geometry_in_repo": "no (metadata only)", "area_km2": ""},
}
OSM_API = "https://api.openstreetmap.org/api/0.6/relation/{}.json"
OSM_FULL = "https://api.openstreetmap.org/api/0.6/relation/{}/full"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_boundary_comparison():
    rows = []
    for rid, m in OSM_RELATIONS.items():
        geom_available = m["geometry_in_repo"].startswith("yes")
        parts = holes = valid = area = ""
        if geom_available:
            g = OC.load_bender_boundary()[0]
            parts = len(g.geoms) if g.geom_type == "MultiPolygon" else 1
            holes = (len(g.interiors) if g.geom_type == "Polygon"
                     else sum(len(p.interiors) for p in g.geoms))
            valid = g.is_valid
            area = m["area_km2"]
        rows.append({
            "candidate_id": f"osm_relation_{rid}", "relation_id": rid,
            "osm_url": OSM_API.format(rid), "name": m["name"],
            "object_type": m["type"], "boundary": m["boundary"],
            "admin_level": m["admin_level"], "place": m["place"],
            "version": m["version"], "timestamp": m["timestamp"],
            "changeset": m["changeset"], "retrieved_utc": "2026-07-31",
            "license": "ODbL (OpenStreetMap)", "crs": "EPSG:4326",
            "geometry_in_repo": m["geometry_in_repo"],
            "geometry_type": ("Polygon/MultiPolygon" if geom_available else ""),
            "valid": valid, "area_km2": area, "polygon_parts": parts, "holes": holes,
            "geometry_fetch_url": OSM_FULL.format(rid),
            "verification_status": "PROVISIONAL_PROXY" if rid == "12463379"
            else "METADATA_ONLY_GEOMETRY_NOT_FETCHED",
            "suitability_note": _suitability(rid, m),
        })
    header = list(rows[0].keys())
    with COMPARE_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


def _suitability(rid, m):
    if rid == "12463379":
        return ("admin_level 8 city proper; repo calls it a provisional proxy for "
                "the tariff switch point — NOT proven to be the operational boundary")
    if rid == "9581354":
        return ("admin_level 4 municipality — LARGER; likely includes Гиска / "
                "Протягайловка / Северный inside the city, which would remove their "
                "external surcharge. Geometry must be fetched to confirm.")
    return ("admin_level 5 de-facto PMR municipality; geometry must be fetched to "
            "assess inside/outside classification")


# ----------------------- owner map -----------------------

def _load_polygon_rings(path, key_field, wanted):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        key = f["properties"].get(key_field)
        if key not in wanted:
            continue
        geom = shape(f["geometry"])
        rings = []
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            rings.append(list(p.exterior.coords))
        out[key] = rings
    return out


def _simplify(coords, stride):
    if len(coords) <= 4:
        return coords
    kept = coords[::stride]
    if kept[-1] != coords[-1]:
        kept = [*kept, coords[-1]]
    return kept


def build_map():
    bender_rings = _load_polygon_rings(BOUNDARIES, "key", {"bender"})
    settle = _load_polygon_rings(SETTLEMENTS, "key",
                                 {"bender", "parkany", "giska", "protyagailovka"})
    routes = [(uid, inv["coords"])
              for uid, inv in OC.build_inventory(
                  [r for r in OC.ZE.ZM.load_addresses()
                   if r["settlement"] in OC.EXTERNAL_SETTLEMENTS],
                  {r["uid"]: r for r in OC.ZE.ZM.load_addresses()})[0].items()
              if inv.get("coords")]
    fees = OC._csv(FEES_CSV) if hasattr(OC, "_csv") else _read(FEES_CSV)
    ext_points = [(float(r["longitude"]), float(r["latitude"]), r["territory"])
                  for r in fees if r["latitude"] != ""]
    sample = ext_points[::max(1, len(ext_points) // 500)]  # clustered subset for the map

    all_lon = [c[0] for rings in list(bender_rings.values()) + list(settle.values())
               for ring in rings for c in ring]
    all_lat = [c[1] for rings in list(bender_rings.values()) + list(settle.values())
               for ring in rings for c in ring]
    all_lon += [x for _, x in [(0, p[0]) for p in sample]]
    all_lat += [y for _, y in [(0, p[1]) for p in sample]]
    for _uid, coords in routes:
        all_lon += [c[0] for c in coords]
        all_lat += [c[1] for c in coords]
    lon0, lon1 = min(all_lon), max(all_lon)
    lat0, lat1 = min(all_lat), max(all_lat)
    W, H, M = 960, 720, 24
    sx = (W - 2 * M) / (lon1 - lon0)
    sy = (H - 2 * M) / (lat1 - lat0)
    s = min(sx, sy)

    def px(lon, lat):
        x = M + (lon - lon0) * s
        y = H - M - (lat - lat0) * s
        return f"{x:.1f},{y:.1f}"

    def path(coords, stride=1):
        pts = " ".join(px(x, y) for x, y in _simplify(coords, stride))
        return pts

    groups = []
    # settlements
    colors = {"parkany": "#7b2cbf", "giska": "#2a9d3f", "protyagailovka": "#f07f14",
              "bender": "#888"}
    for key, rings in settle.items():
        polys = "".join(
            f'<polygon points="{path(r, 3)}" fill="{colors.get(key, "#999")}" '
            f'fill-opacity="0.12" stroke="{colors.get(key, "#999")}" '
            f'stroke-width="1" stroke-dasharray="4 3"/>' for r in rings)
        groups.append(f'<g id="settle_{key}" class="layer">{polys}</g>')
    # bender admin_level 8 boundary (provisional)
    for r in bender_rings.get("bender", []):
        groups.append(
            f'<g id="boundary_12463379" class="layer">'
            f'<polygon points="{path(r, 2)}" fill="#d62828" fill-opacity="0.06" '
            f'stroke="#d62828" stroke-width="2"/></g>')
    # routes
    rline = "".join(
        f'<polyline points="{path(c, 1)}" fill="none" stroke="#1f77b4" '
        f'stroke-width="1.4" stroke-opacity="0.85"/>' for _uid, c in routes)
    groups.append(f'<g id="routes" class="layer">{rline}</g>')
    # external address points (sampled)
    pcol = {"Парканы": "#7b2cbf", "Гиска": "#2a9d3f", "Протягайловка": "#f07f14"}
    dots = "".join(
        f'<circle cx="{px(x, y).split(",")[0]}" cy="{px(x, y).split(",")[1]}" '
        f'r="1.6" fill="{pcol.get(t, "#333")}" fill-opacity="0.6"/>'
        for x, y, t in sample)
    groups.append(f'<g id="points" class="layer">{dots}</g>')

    legend = "".join([
        '<g id="legend" font-size="12" font-family="system-ui">',
        '<rect x="20" y="20" width="330" height="120" fill="#fff" '
        'fill-opacity="0.9" stroke="#ccc"/>',
        '<text x="30" y="40" font-weight="bold">Слои (источники)</text>',
        '<text x="30" y="60" fill="#d62828">'
        '■ Граница Бендер OSM r12463379 (level 8, PROVISIONAL)</text>',
        '<text x="30" y="78" fill="#7b2cbf">■ Парканы</text>',
        '<text x="120" y="78" fill="#2a9d3f">■ Гиска</text>',
        '<text x="185" y="78" fill="#f07f14">'
        '■ Протягайловка (settlements.geojson)</text>',
        '<text x="30" y="96" fill="#1f77b4">'
        '— 12 route polylines (central origin)</text>',
        '<text x="30" y="114" fill="#333">'
        '• внешние canonical address points (выборка)</text>',
        '<text x="30" y="132" fill="#666">'
        'r9581354 (level 4), r944727 (level 5): геометрии нет в репо</text>',
        '</g>'])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}">{"".join(groups)}{legend}</svg>')
    MAP_SVG.write_text(svg, encoding="utf-8", newline="\n")

    toggles = "".join(
        f'<label><input type="checkbox" checked onchange="t(this,\'{gid}\')"> {gid}</label> '
        for gid in ("boundary_12463379", "settle_parkany", "settle_giska",
                    "settle_protyagailovka", "settle_bender", "routes", "points"))
    html = (
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Owner boundary map — external tariff</title>"
        "<style>body{font:14px system-ui;margin:12px}#c label{margin-right:10px}</style>"
        "</head><body>"
        "<h2>Карта тарифной границы (кандидаты) — analysis, не production</h2>"
        "<p>Границы OSM r9581354 (муниципий, level 4) и r944727 (level 5) показаны только "
        "в таблице кандидатов — их геометрии нет в репозитории. r12463379 — provisional.</p>"
        f"<div id='c'>{toggles}</div>{svg}"
        "<script>function t(cb,id){document.getElementById(id).style.display="
        "cb.checked?'':'none';}</script></body></html>")
    MAP_HTML.write_text(html, encoding="utf-8", newline="\n")
    _rasterize_svg(svg, W, H)
    return len(routes), len(sample), len(ext_points)


def _rasterize_svg(svg, W, H):
    """Deterministic PNG preview of the SVG via Pillow (parses the emitted
    primitives). Skipped cleanly if Pillow is unavailable — the SVG stays canonical.
    """
    import re
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        return
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def pts(s):
        v = [float(x) for x in re.findall(r"[-+]?\d+\.?\d*", s)]
        return list(zip(v[0::2], v[1::2], strict=False))

    for m in re.finditer(
            r'<polygon points="([^"]+)"[^>]*stroke="([^"]+)"[^>]*stroke-width="([\d.]+)"',
            svg):
        p = pts(m.group(1))
        if len(p) > 1:
            d.line([*p, p[0]], fill=m.group(2), width=int(float(m.group(3))))
    for m in re.finditer(r'<polyline points="([^"]+)"', svg):
        p = pts(m.group(1))
        if len(p) > 1:
            d.line(p, fill="#1f77b4", width=1)
    for m in re.finditer(
            r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="([^"]+)"', svg):
        x, y, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
        d.ellipse([x - r - 0.5, y - r - 0.5, x + r + 0.5, y + r + 0.5], fill=m.group(4))
    d.rectangle([20, 20, 350, 140], outline="#ccc")
    for x, y, t, c in [
            (30, 30, "Layers (analysis, not production)", "#000"),
            (30, 50, "Bender OSM r12463379 (level 8, PROVISIONAL)", "#d62828"),
            (30, 68, "Parkany / Giska / Protyagailovka", "#7b2cbf"),
            (30, 86, "12 route polylines (central origin)", "#1f77b4"),
            (30, 104, "external address points (sample)", "#333"),
            (30, 122, "r9581354(L4), r944727(L5): no geom in repo", "#666")]:
        d.text((x, y), t, fill=c)
    img.save(MAP_PNG)


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


# ----------------------- documents -----------------------

def write_documents(compare, scen_rows, n_routes, n_sample, n_points):
    _provider_md()
    _pilot_md()
    _decision_md(compare, scen_rows)


def _provider_md():
    PROVIDER_MD.write_text("\n".join([
        "# Route provider investigation v1", "",
        "Canonical `route_km` provenance (from the repo, reproducible):", "",
        "- Provider: **OSRM v26.7.3**, local server `http://127.0.0.1:5000` "
        "(scripts/stage09_engine.py).",
        "- Profile: **car.lua** + custom `endpoint-aware-delivery.1` access profile and "
        "ordered turn-restriction parser (docs/data/stage10c-osrm-build-manifest.json, "
        "stage10d-graph-provenance.json).",
        "- Source graph: **moldova-latest.osm.pbf** sha256 09ba0c058e89… "
        "(matches registry source_dataset_version `moldova-pbf:09ba0c058e89`).",
        "- Origins: **central 46.82388,29.48313** (weight 0.85) + bam + outer; "
        "`central_km` is the fixed-origin route, `expected_km` a blend.", "",
        "## Critical limitation", "",
        "Canonical `route_km` is measured **from a single central point**, not from "
        "each restaurant. A real order's price must be routed from the ORDERING "
        "restaurant to the client. **The current canonical route_km is therefore a "
        "proxy and is NOT suitable as a universal production price for all "
        "restaurants** — per-restaurant routing (per restaurant origin) is required "
        "for a production tariff.", "",
        "## Reproducibility", "",
        "Routes are reproducible with: the recorded moldova PBF (sha256 above), OSRM "
        "v26.7.3, the car.lua profile (sha256 in the manifest), and the delivery "
        "access/restriction profile versions. Free, local, no rate limit, no API "
        "cost. The OSRM engine is not running in this analysis environment and the "
        "100 MB PBF is not in the clone (gitignored), so no live routing runs here.",
        "",
    ]), encoding="utf-8", newline="\n")


def _pilot_md():
    PILOT_MD.write_text("\n".join([
        "# Route generation pilot v1", "",
        "**Status: BLOCKED_IN_THIS_ENV (no live OSRM engine / PBF here).** No live "
        "or paid batch was run; nothing invented.", "",
        "## Reproducible pilot plan (analysis-only, ≥30 addresses)", "",
        "1. Stand up OSRM v26.7.3 with the recorded moldova PBF + car.lua "
        "(`scripts/build_osrm_with_manifest.sh`).",
        "2. Select ≥30 external addresses spanning Парканы/Гиска/Протягайловка, "
        "near-boundary, min-route, max-route and anomalies (deterministic from the "
        "canonical set).",
        "3. Request the **full route polyline** per address from the central origin "
        "(and, for production, from each restaurant origin).",
        "4. Compare polyline length vs canonical `route_km`; store raw responses + "
        "sha256 + provenance; assert deterministic, resumable, cached output.", "",
        "## Estimate for the full 4,338-route batch", "",
        "- Engine: **local OSRM** — free, no API cost, no rate limit.",
        "- Time: a local OSRM `/route` batch of ~4,338 requests completes in seconds "
        "to a few minutes on commodity hardware.",
        "- The real cost is standing up the engine + 100 MB PBF, not per-request.",
        "- Do NOT switch to a different provider without a comparison analysis; a "
        "different engine/profile would change route_km and cannot be silently "
        "substituted for the canonical provider.", "",
        "**Owner permission is required before running the full batch.** This step "
        "only documents the plan; it does not run it.", "",
    ]), encoding="utf-8", newline="\n")


def _decision_md(compare, scen_rows):
    changed = [r for r in scen_rows]  # 12 routed addresses with a scenario price
    lines = [
        "# OWNER_BOUNDARY_DECISION", "",
        "## Проблема (кратко)", "",
        "Внешняя доплата к тарифу зависит от того, ГДЕ проходит городская граница. "
        "В репозитории граница Бендер (OSM r12463379, admin_level 8) прямо помечена "
        "как *provisional proxy* — не доказано, что это утверждённая тарифная "
        "граница. Есть ещё два кандидата (r9581354 муниципий level 4, r944727 level "
        "5), но их геометрии в репозитории нет. Пока граница не подтверждена, "
        "утверждённых внешних цен нет.", "",
        "## Карта", "",
        "См. `owner-boundary-map-v1.html` (self-contained, слои переключаются), "
        "`owner-boundary-map-v1.svg` и `owner-boundary-map-v1.png` (превью). Показаны: "
        "граница r12463379, полигоны Бендер/Парканы/Гиска/Протягайловка, 12 "
        "существующих маршрутов, выборка внешних адресов.", "",
        "## Кандидаты границы", "",
        "| Кандидат | admin_level | что это | геометрия в репо | статус |",
        "|---|---|---|---|---|",
    ]
    for c in compare:
        lines.append(f"| {c['candidate_id']} | {c['admin_level']} | {c['name']} "
                     f"({c['place']}) | {c['geometry_in_repo']} | {c['verification_status']} |")
    lines += [
        "", "## Что рекомендуется (НЕ утверждено)", "",
        "**Рекомендация: как «город» для тарифа логичнее всего admin_level 8 "
        "(r12463379) — это собственно город Бендеры.** НО репозиторий сам называет её "
        "provisional, и точная точка переключения тарифа не доказана. Муниципий "
        "(r9581354, level 4) — крупнее и, вероятно, включает Гиску/Протягайловку "
        "внутрь города (тогда у них не будет доплаты, кроме минимума). Это "
        "принципиально разные решения по цене. **Клод не выбирает за владельца.**", "",
        "## Территории и где начинается доплата", "",
        "- Если граница = r12463379 (город): Парканы/Гиска/Протягайловка — снаружи, "
        "доплата от точки выезда за границу (мин 5 MDL).",
        "- Если граница = r9581354 (муниципий): часть этих сёл может оказаться внутри "
        "→ доплаты нет или только минимум. Нужно скачать геометрию, чтобы посчитать.",
        "- Северный: в canonical 9,216 отсутствует (TERRITORY_DATA_UNAVAILABLE).", "",
        "## Влияние на цену (12 существующих маршрутов, только r12463379)", "",
        "Это SCENARIO по provisional границе, НЕ утверждённая цена:", "",
        "| address_id | territory | outside_km | surcharge | scenario_final |",
        "|---|---|---:|---:|---:|",
    ]
    for r in changed:
        lines.append(f"| {r['canonical_address_id']} | {r['territory']} | "
                     f"{r['scenario_outside_city_km']} | "
                     f"{r['scenario_external_surcharge']} | {r['scenario_final_fee']} |")
    lines += [
        "", "После исправления min-surcharge 4 адреса Гиски с outside=0 получают "
        "доплату **5** (было 0) → scenario_final 22 (было 17).", "",
        "## Риски", "",
        "- Выбор границы меняет, кто платит внешнюю доплату (тысячи адресов).",
        "- canonical route_km считался от ОДНОЙ центральной точки — для production "
        "цены нужен маршрут от конкретного ресторана (см. route-provider-investigation).",
        "- Для 4,338 из 4,350 внешних адресов polyline ещё НЕ построены.", "",
        "## Что произойдёт после утверждения", "",
        "После утверждения границы владельцем: (1) при необходимости скачивается "
        "геометрия выбранной relation; (2) строятся polyline для оставшихся 4,338 "
        "адресов тем же OSRM (см. pilot); (3) считается outside_city_km и цена. "
        "Ничего не применяется в production без отдельного шага.", "",
        "## ⚠ Ещё нужны polylines для 4,338 адресов", "",
        "Подтверждение границы НЕ создаёт маршруты. Для 4,338 внешних адресов route "
        "geometry отсутствует — нужен pilot + полный batch (см. "
        "`route-generation-pilot-v1.md`), с отдельного разрешения владельца.", "",
        "## OWNER DECISION REQUIRED", "",
        "```",
        "[ ] Approve candidate A — OSM r12463379 (город, admin_level 8)",
        "[ ] Approve candidate B — OSM r9581354 (муниципий, level 4) [нужна геометрия]",
        "[ ] Approve draft operational boundary C [не создана — нет доказуемой основы]",
        "[ ] Reject all and revise",
        "```", "",
        "Ни один пункт не отмечен. **VERDICT: OWNER_BOUNDARY_DECISION_REQUIRED.**", "",
    ]
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main():
    compare = write_boundary_comparison()
    n_routes, n_sample, n_points = build_map()
    scen_rows = _read(SCEN_CSV)
    write_documents(compare, scen_rows, n_routes, n_sample, n_points)
    print(json.dumps({"boundary_candidates": len(compare), "map_routes": n_routes,
                      "map_points_sampled": n_sample, "total_points": n_points,
                      "scenario_rows": len(scen_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
