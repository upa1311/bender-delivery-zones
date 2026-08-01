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
SCEN_SUMMARY = RZ / "_boundary-scenarios-summary.json"
PILOT_SUMMARY = ROOT / "data/interim/route-pilot/route-pilot-summary-v1.json"


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
        "## Кандидаты границы (реально извлечены)", "",
        "| relation | admin_level | смысл | площадь км² | тип | внешних точек внутри |",
        "|---|---|---|---:|---|---:|",
    ]
    for rid in ("12463379", "9581354", "944727"):
        r = by_id[rid]
        lines.append(f"| {rid} | {r['admin_level']} | {r['name']} | {r['area_km2']} | "
                     f"{r['geometry_type']} | {r['external_points_inside']} |")
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
        "## Влияние на цену — 12 маршрутов × 3 границы", "",
        "Полная таблица: `boundary-route-scenarios-v2.csv` (36 строк). Для каждой "
        "комбинации есть ДВА чтения:",
        "- `geometric_*` — классификация по попаданию точки в полигон;",
        "- `territory_rule_*` — правило метки (Парканы/Гиска/Протягайловка = внешние, "
        "минимум 5 применяется даже при outside_km = 0).", "",
        f"Адресов, где ГЕОМЕТРИЯ границы меняет цену/классификацию: "
        f"**{len(scen['price_or_class_changing_addresses'])}**. "
        f"Конфликтов «метка vs геометрия»: **{len(scen['label_geometry_conflicts'])}**.",
        "", "## Объяснение Гиски (важно)", "",
        f"Центроид Гиски снаружи r12463379, НО **{scen['giska_inside_12463379_points']} "
        "адресов Гиски геометрически попадают ВНУТРЬ** admin_level-8 линии — граница "
        "срезает край села. Четыре маршрутных адреса Гиски "
        "(w353619672/w353817270/w353817271/w353817272) с outside_km = 0:",
        "- по ГЕОМЕТРИИ они внутри → городской тариф 17;",
        "- по МЕТКЕ (Гиска = внешняя территория) → минимум 5 → 22 (как в v1-фиксе).",
        "Это и есть решение владельца: считать такие адреса городом (геометрия) или "
        "внешними (метка). Claude не выбирает.", "",
        "## Пост ГАИ на Котовского и корридоры", "",
        "В `external-tariff-boundary-anchors-v1.csv` пост ГАИ (PARKANY_KOTOVSKOGO_"
        "GAI_POST) помечен `OWNER_BRIEF_ONLY`, `UNPROVEN`, **без координат** — «no "
        "coordinates invented». На карте показан только в таблице якорей, НЕ "
        "наносится выдуманной точкой. Гиска/Протягайловка/Северный anchors — тоже "
        "UNPROVEN.", "",
        "## Результат 30-address pilot", "",
        f"Реальный запуск (ALTERNATIVE_PROVIDER_COMPARISON, OSRM demo, тот же "
        f"центральный origin): attempted {pilot['attempted']}, succeeded "
        f"{pilot['succeeded']}, failed {pilot['failed']}; "
        f"{pilot['never_routed_before']} адресов ранее без polyline; |Δ| к canonical "
        f"route_km: mean {pilot['abs_diff_km_mean']} км, max {pilot['abs_diff_km_max']} "
        "км. Canonical route_km считается от ОДНОГО центрального ресторана — для "
        "production нужен маршрут от конкретного ресторана. Alt-provider нельзя "
        "принять в production (другой граф/профиль). Подробно: "
        "`route-generation-pilot-v1.md`.", "",
        "## ⚠ 4 338 отсутствующих production polylines", "",
        "Подтверждение границы НЕ создаёт маршруты. Для ~4 338 внешних адресов нет "
        "canonical polyline. Полный batch — локальным OSRM (бесплатно, минуты), "
        "с отдельного разрешения владельца. НЕ запущен.", "",
        "## Рекомендация (после фактического сравнения; НЕ утверждение)", "",
        "Три границы = три определения «города»:",
        "- **r12463379 (21 км²)** — узкий город: почти все внешние адреса платят "
        "доплату; максимальная выручка с доплат, но Протягайловка/Северный «внешние».",
        "- **r9581354 (37.7 км², де-юре)** — Протягайловка становится городом "
        "(505 адресов), Гиска/Северный остаются внешними.",
        "- **r944727 (72 км², де-факто ПМР)** — и Протягайловка, и большая часть "
        "Гиски, и Северный — город; внешними остаются в основном Парканы.",
        "Наиболее соответствует «фактическому городу под управлением ПМР» — **944727**, "
        "но это политически/юридически чувствительный выбор (де-факто vs де-юре), и "
        "**решение за владельцем**. Границы уверенности: геометрии реальны и "
        "воспроизводимы, но привязка тарифа к админ-границе — управленческое "
        "решение, не автоматическое.", "",
        "## Что дальше после решения владельца", "",
        "(1) зафиксировать выбранную границу; (2) построить 4 338 polylines "
        "каноническим OSRM; (3) классифицировать адреса и посчитать цену; "
        "(4) отдельным шагом внести в production. Ничего не применяется автоматически.",
        "", "## OWNER DECISION REQUIRED", "",
        "```",
        "[ ] Approve candidate A — OSM r12463379 (city, admin_level 8, 21 km²)",
        "[ ] Approve candidate B — OSM r9581354 (municipality, level 4, 37.7 km²)",
        "[ ] Approve draft operational boundary C — OSM r944727 (de-facto PMR, level "
        "5, 72 km²) as DRAFT_UNAPPROVED",
        "[ ] Reject all and revise",
        "```", "",
        "Ни один пункт не отмечен. Ни одна граница не VERIFIED_FOR_TARIFF; "
        "production final_fee пуст; массовый batch не запущен.",
        "**VERDICT: OWNER_BOUNDARY_DECISION_REQUIRED.**", "",
    ]
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main():
    _run("extract_osm_boundaries", "scripts/extract_osm_boundaries.py")
    _run("boundary_scenarios", "scripts/boundary_scenarios.py")
    _run("owner_map_v2", "scripts/owner_map_v2.py")
    _run("route_pilot", "scripts/route_pilot.py")
    inventory = write_inventory()
    severny_mem = write_severny()
    write_decision(inventory, severny_mem)
    print(json.dumps({"inventory_sources": len(inventory),
                      "severny_in_944727": severny_mem["944727"]["inside"],
                      "decision_doc": str(DECISION_MD.relative_to(ROOT))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
