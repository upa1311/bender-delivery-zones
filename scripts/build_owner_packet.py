"""Single reproducibility entrypoint for the owner boundary decision packet.

Running `python scripts/build_owner_packet.py` regenerates, from committed/raw local
inputs only (cached OSM + pilot raw responses, NO forced network):
  1. extracted boundary geometries + provenance   (extract_osm_boundaries, cached)
  2. boundary comparison + route scenarios         (boundary_scenarios)
  3. full owner map HTML + PNG/SVG                 (owner_map_v2)
  4. route pilot summary from saved raw responses  (route_pilot, cached)
  5. source inventory, Северный report, OWNER_BOUNDARY_DECISION.md  (this script)

Nothing is applied to production; no boundary is marked VERIFIED_FOR_TARIFF and no
owner checkbox is pre-checked. After a run the working tree stays clean.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RZ = ROOT / "reports/zone-model-audit"
INVENTORY_CSV = ROOT / "data/interim/source-inventory-v1.csv"
SEVERNY_MD = RZ / "severny-investigation-v1.md"
DECISION_MD = RZ / "OWNER_BOUNDARY_DECISION.md"
COMPARE_CSV = ROOT / "data/interim/boundary-candidates-comparison-v2.csv"
SCEN_CSV = ROOT / "data/interim/boundary-route-scenarios-v2.csv"
SCEN_SUMMARY = RZ / "_boundary-scenarios-summary.json"
PILOT_SUMMARY = ROOT / "data/interim/route-pilot/route-pilot-summary-v1.json"
RESTAURANT_PLAN_MD = RZ / "restaurant-origins-plan-v1.md"


def _run(mod_name, rel):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
    return mod


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------- source inventory ---------------------------
SOURCES = [
    ("reports/stage-01/source-audit.md", "Stage-01 OSM source audit (PBF + 2 brief "
     "boundary candidates)", "generated", "stage-01 pipeline over Moldova PBF", True),
    ("reports/stage-01/source-audit.json", "Machine-readable stage-01 audit "
     "(candidate tags/metrics)", "generated", "stage-01 pipeline", True),
    ("config/boundary-candidates.yml", "Brief boundary candidate ids (9581354, "
     "944727) — inspect only", "raw", "project brief", True),
    ("docs/data/source-boundaries.geojson", "Repo provisional Bender boundary "
     "(relation 12463379)", "generated", "earlier stage; provisional proxy", True),
    ("docs/data/settlements.geojson", "Settlement polygons Парканы/Гиска/"
     "Протягайловка/Бендеры", "generated", "OSM-derived", True),
    ("docs/data/restaurant-origins.geojson", "3 confirmed restaurant origins "
     "(central/bam/outer) for routing", "generated", "stage-09 engine", True),
    ("docs/data/severny-service-area.geojson", "Северный candidate residential "
     "footprint (owner_review)", "generated", "severny footprint stage", True),
    ("docs/data/severny-delivery-units.geojson", "57 Северный delivery units with "
     "central_km", "generated", "severny stage", True),
    ("data/interim/external-tariff-boundary-anchors-v1.csv", "External tariff anchors "
     "incl. пост ГАИ Котовского (no coords, UNPROVEN)", "generated", "owner brief + "
     "GIS review", True),
    ("data/interim/osm-boundaries/boundary-extraction-provenance.json", "Provenance "
     "of the 3 freshly-extracted OSM geometries", "generated",
     "scripts/extract_osm_boundaries.py via Overpass", True),
    ("data/interim/osm-boundaries/relation-12463379.geojson", "Extracted geometry "
     "r12463379 (level 8)", "generated", "Overpass out geom", True),
    ("data/interim/osm-boundaries/relation-9581354.geojson", "Extracted geometry "
     "r9581354 (level 4)", "generated", "Overpass out geom", True),
    ("data/interim/osm-boundaries/relation-944727.geojson", "Extracted geometry "
     "r944727 (level 5)", "generated", "Overpass out geom", True),
    ("data/interim/route-pilot/route-pilot-summary-v1.json", "30-address pilot summary "
     "(alt-provider comparison)", "generated", "scripts/route_pilot.py via OSRM demo",
     True),
]


def write_inventory():
    rows = []
    for rel, purpose, kind, prov, repro in SOURCES:
        p = ROOT / rel
        exists = p.exists()
        rows.append({
            "path": rel, "purpose": purpose, "format": p.suffix.lstrip(".") or "?",
            "exists": exists, "size_bytes": p.stat().st_size if exists else 0,
            "sha256": _sha(p) if exists else "",
            "raw_or_generated": kind, "provenance": prov,
            "relation_to_canonical": "analysis-only; not production",
            "reproducible": repro,
        })
    with INVENTORY_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


# --------------------------- Северный report ---------------------------
def _severny_membership():
    from shapely.geometry import Point, shape
    bnd = {rid: shape(json.loads((ROOT / f"data/interim/osm-boundaries/relation-{rid}"
                                  ".geojson").read_text(encoding="utf-8"))["geometry"])
           for rid in ("12463379", "9581354", "944727")}
    du = json.loads((ROOT / "docs/data/severny-delivery-units.geojson")
                    .read_text(encoding="utf-8"))["features"]
    out = {}
    for rid, b in bnd.items():
        inside = sum(1 for f in du if b.contains(Point(*f["geometry"]["coordinates"])))
        out[rid] = {"inside": inside, "outside": len(du) - inside}
    return out, len(du)


def write_severny():
    sa = json.loads((ROOT / "docs/data/severny-service-area.geojson")
                    .read_text(encoding="utf-8"))["features"][0]["properties"]
    mem, n = _severny_membership()
    lines = [
        "# Северный re-investigation v1", "",
        "**Prior verdict corrected.** Северный is NOT globally "
        "`TERRITORY_DATA_UNAVAILABLE`. It is absent from the canonical 9,216 pricing "
        "set, but a dedicated stage produced real candidate data.", "",
        "## Sources checked (Cyrillic + Latin aliases)", "",
        "- `docs/data/severny-service-area.geojson` — 1 candidate residential "
        "footprint polygon.",
        "- `docs/data/severny-delivery-units.geojson` — 57 delivery units WITH "
        "`central_km` (route distance from the central origin).",
        "- `docs/data/severny-candidate-buildings.geojson` — 59 raw candidate "
        "buildings.",
        "- `docs/data/severny-route-qa.geojson` — 58 route-QA polylines.",
        "- Canonical address set (`outside-city-distance-v1.csv`, 9,216) — Северный "
        "NOT present.",
        "- `external-tariff-boundary-anchors-v1.csv` — SEVERNY_BOUNDARY UNPROVEN.",
        "- Aliases searched: Северный / Severny / Severnyy / Nord / микрорайон "
        "Северный / Северная.", "",
        "## What the data says", "",
        f"- Real place: `{sa.get('district_label_ru')}` (place=suburb node "
        "5135654201), north of Varniţa village.",
        f"- Footprint: raw {sa.get('raw_candidate_buildings')} candidate buildings → "
        f"{sa.get('final_included_buildings')} included; "
        f"{sa.get('confirmed_address_count')} confirmed addresses, "
        f"{sa.get('apartment_building_count')} apartment buildings; empty area "
        f"{sa.get('empty_area_pct')}%.",
        f"- Status: `{sa.get('status')}`, resolution `{sa.get('resolution')}`, "
        f"disconnected_from_main_service = {sa.get('disconnected_from_main_service')}.",
        "- Delivery units: 7 `verified_osm_address` + 50 `unaddressed_delivery_unit`; "
        f"all {n} carry `central_km` (6.925–8.726 km).", "",
        "## Северный vs the three candidate boundaries", "",
        "| boundary | Северный units inside | outside |",
        "|---|---:|---:|",
        f"| r12463379 (level 8, city) | {mem['12463379']['inside']} | "
        f"{mem['12463379']['outside']} |",
        f"| r9581354 (level 4, municipality) | {mem['9581354']['inside']} | "
        f"{mem['9581354']['outside']} |",
        f"| r944727 (level 5, de-facto PMR) | {mem['944727']['inside']} | "
        f"{mem['944727']['outside']} |", "",
        "So Северный falls INSIDE only the de-facto PMR city (944727); it is OUTSIDE "
        "both the de-jure municipality and the city-proper. The boundary choice "
        "decides whether Северный is a city district or external.", "",
        "## Honest status", "",
        "**SEVERNY_CANDIDATE_OWNER_REVIEW_REQUIRED** — data exists but is unconfirmed: "
        "the footprint is disconnected from the main service area, 50/57 units are "
        "unaddressed, and the OSM source itself flags `owner_review`. It is NOT in the "
        "canonical pricing set and MUST NOT be priced without owner confirmation.", "",
        "## Reproducible unblocker (analysis-only)", "",
        "To integrate Северный: (1) owner confirms the footprint and which buildings "
        "are real delivery targets; (2) resolve the 50 unaddressed units to canonical "
        "addresses; (3) route each from the required origin with the canonical OSRM; "
        "(4) classify against the chosen boundary. Add as a separate analysis stage — "
        "no production change.", "",
    ]
    SEVERNY_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return mem


# --------------------------- owner decision doc ---------------------------
def write_decision(inventory, severny_mem):
    comp = list(csv.DictReader(COMPARE_CSV.open(encoding="utf-8-sig")))
    scen = json.loads(SCEN_SUMMARY.read_text(encoding="utf-8"))
    pilot = json.loads(PILOT_SUMMARY.read_text(encoding="utf-8"))
    by_id = {r["relation_id"]: r for r in comp}
    scen_rows = list(csv.DictReader(SCEN_CSV.open(encoding="utf-8-sig")))
    per_route = {}
    for r in scen_rows:
        per_route.setdefault(r["canonical_address_id"], {"address": r["address"],
                             "territory": r["territory"], "km": r["canonical_route_km"],
                             "f": {}})["f"][r["boundary_id"]] = int(r["geometric_final_fee"])

    lines = [
        "# OWNER_BOUNDARY_DECISION", "",
        "## Проблема (один абзац)", "",
        "Внешняя доплата зависит от того, где проходит «городская» граница. Есть три "
        "реальные OSM-границы Бендер разного административного смысла и размера "
        "(21 / 37.7 / 72 км²). Все три извлечены из OSM и сравнены на одних данных; "
        "ни одна не является утверждённой тарифной границей. Пока владелец не выбрал "
        "границу, утверждённых внешних цен нет.", "",
        "## Карта", "",
        "`owner-boundary-map-v2.html` (self-contained, слои переключаются, встроены "
        "все 4 350 адресов) + `owner-boundary-map-v2.png/.svg` (превью, три границы "
        "видно раздельно).", "",
        "## Кандидаты границы (реально извлечены — единая семантика)", "",
        "Для каждой relation: owner-label, фактическое OSM-имя, админ-смысл, был ли в "
        "ПЕРВОНАЧАЛЬНОМ brief, входит ли в аналитическое сравнение, tariff-suitability.",
        "",
        "| label | relation | name | admin_level | в brief | candidate | suitability | "
        "площадь км² | внешних точек внутри |",
        "|---|---|---|---|---|---|---|---:|---:|",
    ]
    brief = {"True": "да", "False": "нет"}
    for rid in ("12463379", "9581354", "944727"):
        r = by_id[rid]
        lines.append(
            f"| {r['owner_label']} | {rid} | {r['name']} | {r['admin_level']} | "
            f"{brief.get(r['original_brief_nominated'], r['original_brief_nominated'])} "
            f"| {brief.get(r['comparison_candidate'], r['comparison_candidate'])} | "
            f"{r['tariff_suitability']} | {r['area_km2']} | "
            f"{r['external_points_inside']} |")
    lines += [
        "",
        "**Relation 12463379 — точная семантика:** не была прямо названа в "
        "первоначальном brief (brief перечисляет 9581354 и 944727, "
        "config/boundary-candidates.yml), но обнаружена из source inventory "
        "(source-boundaries.geojson) и включена как аналитический **candidate A**; её "
        "пригодность для тарифа оценивается отдельно (CANDIDATE_UNVERIFIED). Она "
        "остаётся в сравнении и в decision context.",
    ]
    lines += [
        "", "Провенанс (raw sha256): "
        + "; ".join(f"{rid}={by_id[rid]['raw_sha256'][:12]}…"
                    for rid in ("12463379", "9581354", "944727")) + ".", "",
        "## Территории внутри/снаружи (по центроиду)", "",
        "| территория | r12463379 | r9581354 | r944727 |",
        "|---|---|---|---|",
        "| Парканы | out | out | out |",
        "| Гиска | out | out | **in** |",
        "| Протягайловка | out | **in** | **in** |",
        f"| Северный | out ({severny_mem['12463379']['inside']}/57) | "
        f"out ({severny_mem['9581354']['inside']}/57) | "
        f"**in ({severny_mem['944727']['inside']}/57)** |", "",
        "- **Парканы** — снаружи при любом выборе (доплата в любом случае).",
        "- **Гиска/Протягайловка/Северный** — зависят от выбора границы.", "",
        "## Влияние на цену — все 12 маршрутов × 3 границы", "",
        "geometric_final_fee (город = базовый тариф; вне = базовый + доплата). "
        "Полная таблица с пересечениями/метка-vs-геометрия: "
        "`boundary-route-scenarios-v2.csv` (36 строк).", "",
        "| route_id | address | route_km | A r12463379 | B r9581354 | C r944727 | Δ |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for uid in sorted(per_route):
        p = per_route[uid]
        f = p["f"]
        d = max(f.values()) - min(f.values())
        mark = " ⚠" if d else ""
        lines.append(f"| route_{uid} | {p['address']} | {p['km']} | {f['12463379']} | "
                     f"{f['9581354']} | {f['944727']} |{mark} {d} |")
    changing = [uid for uid, p in per_route.items()
                if max(p["f"].values()) != min(p["f"].values())]
    lines += [
        "", "## Маршруты, где граница МЕНЯЕТ цену/классификацию", "",
        "| address | A r12463379 | B r9581354 | C r944727 | изменение |",
        "|---|---:|---:|---:|---|",
    ]
    for uid in changing:
        p = per_route[uid]
        f = p["f"]
        lines.append(f"| {p['address']} | {f['12463379']} | {f['9581354']} | "
                     f"{f['944727']} | {max(f.values())} → {min(f.values())} MDL |")
    lines += [
        "", "Подтверждённые изменения цены (генерируются из scenario CSV):", "",
        "| Address | Scenario difference |", "| --- | ---: |",
        f"| Гиска, Госпитальная 8 | {per_route['n2321749482']['f']['12463379']} → "
        f"{per_route['n2321749482']['f']['944727']} MDL |",
        f"| Протягайловка, Банный переулок 1 | "
        f"{per_route['w353259234']['f']['12463379']} → "
        f"{per_route['w353259234']['f']['9581354']} MDL |", "",
        "## Объяснение Гиски (важно)", "",
        f"Территория Гиска В ЦЕЛОМ снаружи r12463379 (центроид вне), НО "
        f"**{scen['giska_inside_12463379_points']} конкретных адресов Гиски** "
        "геометрически попадают ВНУТРЬ admin_level-8 линии — граница срезает край "
        "села. Различать: (а) статус территории в целом; (б) статус конкретного "
        "адреса; (в) статус конкретной route polyline. Четыре routed-адреса Гиски "
        "(w353619672/w353817270/w353817271/w353817272), destination которых внутри, "
        "outside_km = 0: по ГЕОМЕТРИИ → город 17; по МЕТКЕ (Гиска = внешняя) → мин 5 → "
        "22. Это решение владельца (геометрия vs метка). Claude не выбирает.", "",
        "## Объяснение Протягайловки", "",
        "Протягайловка снаружи r12463379, но её центроид и большинство адресов ВНУТРИ "
        "r9581354 и r944727. Пример: Банный переулок 1 — вне города по r12463379 "
        f"(final {per_route['w353259234']['f']['12463379']}), но город по r9581354/"
        f"r944727 (final {per_route['w353259234']['f']['9581354']}).", "",
        "## Статус Северного", "",
        "SEVERNY_CANDIDATE_OWNER_REVIEW_REQUIRED — данные есть (57 delivery units с "
        "central_km, service area), но footprint отсоединён, 50/57 адресов не "
        "подтверждены, source помечен owner_review; в canonical 9 216 Северного нет. "
        f"Внутри только r944727 ({severny_mem['944727']['inside']}/57). Подробно: "
        "`severny-investigation-v1.md`.", "",
        "## Пост ГАИ на Котовского и operational tariff boundary", "",
        "Пост ГАИ (PARKANY_KOTOVSKOGO_GAI_POST) — `OWNER_BRIEF_ONLY`, `UNPROVEN`, "
        "**без координат** («no coordinates invented»); показан только в таблице "
        "якорей, не наносится. **Статус отдельной operational-тарифной границы: "
        "`NO_SEPARATE_OPERATIONAL_TARIFF_BOUNDARY_AVAILABLE`** — в репозитории нет "
        "специально разработанной operational-геометрии, и она НЕ создаётся в этом "
        "commit. Три кандидата — это административные OSM-границы, не operational "
        "tariff boundary по умолчанию.", "",
        "## Central-origin limitation и restaurant-specific requirement", "",
        f"30-address pilot ({pilot['classification']}): attempted "
        f"{pilot['attempted']}, succeeded {pilot['succeeded']}, failed "
        f"{pilot['failed']}; {pilot['never_routed_before']} ранее без polyline; |Δ| к "
        f"canonical mean {pilot['abs_diff_km_mean']} км. **Pilot и canonical route_km "
        "считаются от ОДНОЙ центральной представительной точки (кластер ресторанов), "
        "не от конкретного ресторана.** Он годится для проверки routing engine и "
        "воспроизводимости, но НЕ доказывает production-стоимость доставки. Production "
        "routing должен считаться `конкретный ресторан заказа → адрес клиента`. "
        "Координаты ресторанов пока не предоставлены/не подтверждены "
        "(`RESTAURANT_ORIGINS_UNAVAILABLE`, см. `restaurant-origins-plan-v1.md`). "
        "Массовая генерация маршрутов ЗАБЛОКИРОВАНА до restaurant registry и решения "
        "владельца. Подробно: `route-generation-pilot-v1.md`.", "",
        "## Объём полного batch (правильная формула)", "",
        "```", "total_routes = active_restaurant_origins × canonical_delivery_destinations",
        "```",
        "Не «оставшиеся 4 338 маршрутов»: это было бы верно только для ОДНОГО "
        "ресторана. Примеры: 1×4350 = 4 350; 5×4350 = 21 750; 10×4350 = 43 500. "
        "Фактическое число ресторанов неизвестно (registry отсутствует). Batch НЕ "
        "запущен.", "",
        "## Рекомендация (после фактического сравнения; НЕ утверждение)", "",
        "Три границы = три определения «города» (все — административные OSM-границы):",
        "- **A · relation 12463379 · «Бендеры», admin_level 8 (21 км²)** — город "
        "собственно; почти все внешние адреса платят доплату.",
        "- **B · relation 9581354 · «Municipiul Bender», admin_level 4 (37.7 км²)** — "
        "де-юре муниципий РМ; Протягайловка становится городом.",
        "- **C · relation 944727 · «Бендеры/Tighina», admin_level 5 (72 км²)** — "
        "де-факто город под управлением ПМР; и Протягайловка, и часть Гиски, и "
        "Северный — город.",
        "Если нужна именно «фактическая» граница города — это административная "
        "de-facto PMR граница **944727** (НЕ специально разработанная operational "
        "boundary). Выбор политически/юридически чувствителен (де-факто vs де-юре) и "
        "**остаётся за владельцем**. Границы уверенности: геометрии реальны и "
        "воспроизводимы; привязка тарифа к админ-границе — управленческое решение.", "",
        "## Что дальше после решения владельца", "",
        "(1) зафиксировать выбранную relation; (2) получить restaurant registry; "
        "(3) построить маршруты `ресторан → адрес` каноническим OSRM (объём = "
        "рестораны × адреса); (4) классифицировать и посчитать цену; (5) отдельным "
        "шагом внести в production. Ничего не применяется автоматически.", "",
        "## OWNER DECISION REQUIRED", "",
        "```",
        "[ ] Approve relation 12463379 as tariff boundary  "
        "(A · «Бендеры» admin_level 8, 21 km²)",
        "[ ] Approve relation 9581354 as tariff boundary  "
        "(B · «Municipiul Bender» admin_level 4, 37.7 km²)",
        "[ ] Approve relation 944727 as tariff boundary  "
        "(C · de-facto PMR «Бендеры/Tighina» admin_level 5, 72 km²)",
        "[ ] Reject all and request a separate operational tariff boundary",
        "```", "",
        "Ни один пункт не отмечен. Ни одна граница не VERIFIED_FOR_TARIFF; "
        "owner_approval:false; production final_fee пуст; массовый batch не запущен.",
        "**VERDICT: OWNER_BOUNDARY_DECISION_REQUIRED** (+ downstream "
        "`PRODUCTION_ROUTING_BLOCKED_BY_RESTAURANT_ORIGINS`).", "",
    ]
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_restaurant_plan():
    """Restaurant registry status + restaurant-specific routing plan. No restaurant
    coordinates are invented; only the 3 REPRESENTATIVE cluster origins exist."""
    origins = json.loads((ROOT / "docs/data/restaurant-origins.geojson")
                         .read_text(encoding="utf-8"))["features"]
    reps = [(f["properties"].get("key"), f["properties"].get("role"),
             f["properties"].get("poi_count"), f["geometry"]["coordinates"])
            for f in origins]
    dest = 4350
    lines = [
        "# Restaurant-specific routing plan v1", "",
        "## Status: `RESTAURANT_ORIGINS_UNAVAILABLE`", "",
        "The repository has **no per-restaurant registry** (no restaurant_id / name / "
        "canonical address / verified coordinates / active status). It contains only "
        "**3 REPRESENTATIVE cluster origins** (docs/data/restaurant-origins.geojson; "
        "config/demand.yml states POIs are clustered into representative origins, not "
        "treated as complete truth):", "",
        "| key | role | poi_count | lon | lat |", "|---|---|---:|---:|---:|",
    ]
    for key, role, poi, (lon, lat) in reps:
        lines.append(f"| {key} | {role} | {poi} | {lon} | {lat} |")
    lines += [
        "", "These are cluster representatives for a demand model, NOT the coordinates "
        "of individual ordering restaurants. No restaurant coordinates are invented.",
        "", "## Minimum required input schema (owner to provide)", "",
        "```", "restaurant_id           # stable id",
        "restaurant_name         # display name",
        "canonical_address       # settlement, street, house",
        "latitude                # WGS84", "longitude               # WGS84",
        "coordinate_source       # e.g. OSM node, surveyed, owner-provided",
        "verification_status     # verified | unverified",
        "active_status           # active | inactive",
        "delivery_eligibility    # eligible | not", "```", "",
        "## Full-batch scope (formula, not a fixed number)", "",
        "```", "total_routes = active_restaurant_origins × canonical_delivery_destinations",
        "```",
        f"With {dest:,} canonical external destinations (city addresses add more):", "",
        "| restaurants | routes | local OSRM time* | storage** |",
        "|---:|---:|---|---|",
        f"| 1 | {dest:,} | seconds–1 min | ~tens of MB |",
        f"| 5 | {5 * dest:,} | ~minutes | ~hundreds of MB |",
        f"| 10 | {10 * dest:,} | ~minutes | ~hundreds of MB |",
        f"| N (actual, UNKNOWN) | N × {dest:,} | — | — |", "",
        "*Local canonical OSRM `/route`: free, no API cost, no rate limit; time "
        "dominated by engine setup. **Raw + geometry per route. Rate-limit "
        "assumptions: none locally. Expected failures/retries: near-zero locally. "
        "Caching key: `(restaurant_id, canonical_address_id, graph_version)`; resumable "
        "by skipping existing cache entries.", "",
        "## Why the batch is not run", "",
        "No restaurant registry exists, and the central-origin pilot does not prove "
        "per-restaurant production prices. Mass generation is blocked until the owner "
        "provides the registry and approves a boundary. **No batch was run.**", "",
    ]
    RESTAURANT_PLAN_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return len(reps)


def main():
    # sub-steps run in OFFLINE REPLAY mode (no network) — reproduces committed
    # artifacts from cached raw responses. Use --capture on the individual scripts
    # (extract_osm_boundaries.py --capture, route_pilot.py --capture) to refresh raw.
    _run("extract_osm_boundaries", "scripts/extract_osm_boundaries.py")
    _run("outside_city_distance", "scripts/outside_city_distance.py")
    _run("boundary_scenarios", "scripts/boundary_scenarios.py")
    _run("owner_map_v2", "scripts/owner_map_v2.py")
    _run("route_pilot", "scripts/route_pilot.py")
    inventory = write_inventory()
    severny_mem = write_severny()
    reps = write_restaurant_plan()
    write_decision(inventory, severny_mem)
    print(json.dumps({"inventory_sources": len(inventory),
                      "severny_in_944727": severny_mem["944727"]["inside"],
                      "restaurant_cluster_origins": reps,
                      "restaurant_registry": "RESTAURANT_ORIGINS_UNAVAILABLE",
                      "decision_doc": str(DECISION_MD.relative_to(ROOT))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
