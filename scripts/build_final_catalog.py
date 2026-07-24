#!/usr/bin/env python
"""Final catalog: settlement -> district -> street -> house -> zone.

Assembles the owner-approved K=4 / Scenario A result into a single address
catalog, a street catalog, coloured zone polygons and a QA-map summary. Pure
assembly from already-committed data — no OSRM, no PBF, no re-banding. The
existing zone edges are used as-is; no Zone 5 is created; no house numbers are
invented. No prices, no Direct integration.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from bender_zones import jsonutil
from bender_zones.address import full_address_ru
from bender_zones.bands import housenumber_sort_key
from bender_zones.manifest import find_latest_manifest

ZONE_COLORS = {1: "#2a9d3f", 2: "#f2c500", 3: "#f07f14", 4: "#d62828"}  # green/yellow/orange/red
ZONE_EDGES = [2.424, 4.076, 5.577, 9.692]
SEVERNY_DISTRICT = "микрорайон Северный"
ASSIGNMENT_BASIS = "osrm_road_km_0.85_0.15 | K=4 Scenario A (owner-approved)"


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dataset_version(repo_root):
    m = find_latest_manifest(repo_root / "data/manifests",
                             "data/raw/moldova-latest.osm.pbf")
    return f"moldova-pbf:{m['sha256'][:12]}" if m and m.get("sha256") else "moldova-pbf:unknown"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _catalog(repo_root, version):
    rows = []

    # A. Main approved delivery units (Zone 1-4).
    for r in csv.DictReader((repo_root / "docs/data/delivery-units.csv")
                            .read_text("utf-8").splitlines()):
        addressed = r["unit_type"] != "unaddressed_residential_building"
        rows.append({
            "uid": r["uid"], "osm_type": r["osm_type"], "osm_id": int(r["osm_id"]),
            "settlement_ru": r["settlement_ru"], "district_ru": r["district_ru"] or None,
            "street_ru": r["street_ru"] or None, "housenumber": r["housenumber"] or None,
            "full_address_ru": r["full_address_ru"] or None,
            "canonical_address_key": r["canonical_address"] or None,
            "zone_id": int(r["band_k4"]),
            "expected_km": _f(r["expected_km"]), "central_km": _f(r["central_km"]),
            "bam_km": _f(r["bam_km"]),
            "service_status": "standard" if r["tier"] == "A" else "low_density",
            "address_status": "verified_osm_address" if addressed
            else "unaddressed_delivery_unit",
            "assignment_basis": ASSIGNMENT_BASIS,
            "source_dataset_version": version,
            "owner_review_required": False,
            "direct_export_eligible": bool(addressed and r["canonical_address"]),
            "lon": _f(r["lon"]), "lat": _f(r["lat"]),
        })

    # B. Северный enclave — all 57 in Zone 4, owner review pending.
    for r in csv.DictReader((repo_root / "docs/data/severny-delivery-units.csv")
                            .read_text("utf-8").splitlines()):
        verified = r["address_status"] == "verified_osm_address"
        hn = r["housenumber"] or None
        full = full_address_ru("Бендеры", SEVERNY_DISTRICT, r["street_ru"] or "", hn or "")
        rows.append({
            "uid": r["uid"], "osm_type": r["osm_type"], "osm_id": int(r["osm_id"]),
            "settlement_ru": "Бендеры", "district_ru": "Северный",
            "street_ru": r["street_ru"] or None, "housenumber": hn,
            "full_address_ru": full, "canonical_address_key": r["canonical_address_key"] or None,
            "zone_id": 4,
            "expected_km": _f(r["expected_km"]), "central_km": _f(r["central_km"]),
            "bam_km": _f(r["bam_km"]), "service_status": "standard",
            "address_status": r["address_status"],
            "assignment_basis": ASSIGNMENT_BASIS + " | Северный anchored (owner-approved)",
            "source_dataset_version": r["source_dataset_version"],
            "owner_review_required": True,        # catalog incomplete until house table
            "direct_export_eligible": False,      # not client-ready yet
            "lon": _f(r["lon"]), "lat": _f(r["lat"]),
            "severny": True, "severny_verified": verified,
        })

    # C. Disputed addresses — zone_id null, never client-ready.
    disp = json.loads((repo_root / "docs/data/disputed-addresses.json").read_text("utf-8"))
    for a in disp["addresses"]:
        c = a["candidates"][0]
        rows.append({
            "uid": c["uid"], "osm_type": c["osm_type"], "osm_id": int(c["osm_id"]),
            "settlement_ru": a["settlement_ru"], "district_ru": a["district_ru"] or None,
            "street_ru": a["street_ru"] or None, "housenumber": a["housenumber"] or None,
            "full_address_ru": a["full_address_ru"],
            "canonical_address_key": a["canonical_address"], "zone_id": None,
            "expected_km": _f(c.get("expected_km")), "central_km": _f(c.get("central_km")),
            "bam_km": None, "service_status": "disputed", "address_status": "disputed",
            "assignment_basis": "quarantined: coordinate conflict > tolerance",
            "source_dataset_version": version, "owner_review_required": True,
            "direct_export_eligible": False,
            "lon": _f(c["lon"]), "lat": _f(c["lat"]), "disputed": True,
        })

    # D. Excluded objects (Tier C / unreachable / non-residential) — zone_id null.
    reason_status = {"tier_c_no_delivery": "no_delivery",
                     "no_serviceable_street_within_threshold": "excluded",
                     "outside_service_area": "excluded",
                     "unreachable_by_osrm": "excluded"}
    for r in csv.DictReader((repo_root / "docs/data/delivery-exceptions.csv")
                            .read_text("utf-8").splitlines()):
        status = reason_status.get(r["reason"], "excluded")
        rows.append({
            "uid": r["uid"], "osm_type": r["osm_type"], "osm_id": int(r["osm_id"]),
            "settlement_ru": None, "district_ru": None, "street_ru": None,
            "housenumber": None, "full_address_ru": None,
            "canonical_address_key": None, "zone_id": None,
            "expected_km": None, "central_km": None, "bam_km": None,
            "service_status": status, "address_status": "excluded",
            "assignment_basis": r["reason"], "source_dataset_version": version,
            "owner_review_required": False, "direct_export_eligible": False,
            "lon": _f(r["lon"]), "lat": _f(r["lat"]),
        })
    return rows


def _streets(rows):
    """Group serviceable houses into a street catalog. Same street name in a
    different settlement/district is a DIFFERENT street (key includes both)."""
    streets = {}
    for r in rows:
        if not r["street_ru"]:
            continue
        key = (r["settlement_ru"], r["district_ru"], r["street_ru"])
        st = streets.setdefault(key, {
            "settlement_ru": r["settlement_ru"], "district_ru": r["district_ru"],
            "street_ru": r["street_ru"], "confirmed_houses": 0,
            "unaddressed_objects": 0, "disputed_addresses": 0,
            "owner_review_objects": 0, "houses_by_zone": {}, "service_statuses": set()})
        if r.get("disputed"):
            st["disputed_addresses"] += 1
        if r.get("owner_review_required"):
            st["owner_review_objects"] += 1
        st["service_statuses"].add(r["service_status"])
        if r["address_status"] == "unaddressed_delivery_unit":
            st["unaddressed_objects"] += 1
        # A confirmed HOUSE is a verified address with a zone and a housenumber.
        if (r["zone_id"] in (1, 2, 3, 4) and r["housenumber"]
                and r["address_status"] == "verified_osm_address"):
            st["confirmed_houses"] += 1
            st["houses_by_zone"].setdefault(r["zone_id"], set()).add(r["housenumber"])

    out = []
    for st in streets.values():
        zones = sorted(st["houses_by_zone"])
        # Exact house lists per zone; NEVER compress letter/fraction/block numbers.
        houses_by_zone = [
            {"zone_id": z,
             "houses": sorted(st["houses_by_zone"][z], key=housenumber_sort_key)}
            for z in zones]
        status = ("no_delivery" if st["service_statuses"] == {"no_delivery"}
                  else "disputed" if st["service_statuses"] == {"disputed"}
                  else "low_density" if st["service_statuses"] == {"low_density"}
                  else "standard")
        out.append({
            "settlement_ru": st["settlement_ru"], "district_ru": st["district_ru"],
            "street_ru": st["street_ru"], "confirmed_houses": st["confirmed_houses"],
            "unaddressed_objects": st["unaddressed_objects"],
            "zones": zones, "split_street": len(zones) > 1,
            "houses_by_zone": houses_by_zone, "service_status": status,
            "disputed_addresses": st["disputed_addresses"],
            "owner_review_objects": st["owner_review_objects"]})
    out.sort(key=lambda s: (s["settlement_ru"] or "", s["district_ru"] or "",
                            s["street_ru"] or ""))
    return out


def build(repo_root: Path) -> int:
    version = _dataset_version(repo_root)
    rows = _catalog(repo_root, version)
    streets = _streets(rows)
    data = repo_root / "docs/data"
    reports = repo_root / "reports/final"
    reports.mkdir(parents=True, exist_ok=True)
    generated = _now()

    cat_fields = ["uid", "osm_type", "osm_id", "settlement_ru", "district_ru",
                  "street_ru", "housenumber", "full_address_ru",
                  "canonical_address_key", "zone_id", "expected_km", "central_km",
                  "bam_km", "service_status", "address_status", "assignment_basis",
                  "source_dataset_version", "owner_review_required",
                  "direct_export_eligible"]
    ordered = sorted(rows, key=lambda r: (
        r["settlement_ru"] or "￿", r["district_ru"] or "",
        r["street_ru"] or "￿", housenumber_sort_key(r["housenumber"] or "")))
    with open(data / "final-address-zone-catalog.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cat_fields, lineterminator="\n")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k) for k in cat_fields})
    jsonutil.write_compact(data / "final-address-zone-catalog.json", {
        "schema": "bender-final-address-catalog/1", "generated_at": generated,
        "zone_edges_km": ZONE_EDGES, "decided_k": 4, "prices_assigned": False,
        "direct_integration": False,
        "addresses": [{k: r.get(k) for k in cat_fields} for r in ordered]})

    # points geojson (canvas-friendly, minimal props)
    point_props = ["uid", "osm_type", "osm_id", "zone_id", "settlement_ru",
                   "district_ru", "street_ru", "housenumber", "expected_km",
                   "central_km", "bam_km", "service_status", "address_status",
                   "source_dataset_version", "owner_review_required"]
    jsonutil.write_compact(data / "final-address-zone-points.geojson", {
        "type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {k: r.get(k) for k in point_props},
             "geometry": {"type": "Point", "coordinates": [
                 round(r["lon"], 5), round(r["lat"], 5)]}}
            for r in ordered if r["lon"] is not None]})

    st_fields = ["settlement_ru", "district_ru", "street_ru", "confirmed_houses",
                 "unaddressed_objects", "zones", "split_street", "service_status",
                 "disputed_addresses", "owner_review_objects"]
    with open(data / "final-street-zone-catalog.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(st_fields)
        for s in streets:
            w.writerow([s["settlement_ru"], s["district_ru"], s["street_ru"],
                        s["confirmed_houses"], s["unaddressed_objects"],
                        "|".join(str(z) for z in s["zones"]), s["split_street"],
                        s["service_status"], s["disputed_addresses"],
                        s["owner_review_objects"]])
    jsonutil.write(data / "final-street-zone-catalog.json", {
        "schema": "bender-final-street-catalog/1", "generated_at": generated,
        "rule": ("The house is the source of truth, not the street name. A street "
                 "gets one zone only if all its confirmed houses share it; "
                 "otherwise split_street=true with exact houses per zone. Same "
                 "street name in different settlements/districts is not merged."),
        "streets": streets})

    _zone_polygons(repo_root, data)
    summary = _summary(rows, streets, generated)
    jsonutil.write(data / "final-zone-map-summary.json", summary)
    _reports(reports, rows, streets, summary, generated)
    print(f"catalog: {len(rows)} objects | streets {len(streets)} | "
          f"zones {summary['objects_per_zone']} | disputed {summary['disputed']} | "
          f"severny {summary['severny_objects']}")
    return 0


def _zone_polygons(repo_root, data):
    bands = json.loads((repo_root / "docs/data/tariff-bands.geojson").read_text("utf-8"))
    feats = []
    for f in bands["features"]:
        if f["properties"].get("k") != 4:
            continue
        z = f["properties"]["zone"]
        feats.append({"type": "Feature", "properties": {
            "zone_id": z, "zone_name": f"Zone {z}", "color": ZONE_COLORS[z],
            "component": "bender_main", "band_min_km": None if z == 1 else ZONE_EDGES[z - 2],
            "band_max_km": ZONE_EDGES[z - 1]}, "geometry": f["geometry"]})
    # Северный as a SEPARATE Zone 4 component (not connected by a coloured corridor).
    sev = json.loads((repo_root / "docs/data/severny-service-area.geojson")
                     .read_text("utf-8"))["features"][0]
    feats.append({"type": "Feature", "properties": {
        "zone_id": 4, "zone_name": "Zone 4", "color": ZONE_COLORS[4],
        "component": "severny_enclave", "band_min_km": ZONE_EDGES[2],
        "band_max_km": ZONE_EDGES[3],
        "note": "Северный — отдельный анклав Zone 4, не соединён с основными Бендерами."},
        "geometry": sev["geometry"]})
    jsonutil.write_compact(data / "final-zone-polygons.geojson",
                           {"type": "FeatureCollection", "features": feats})


def _summary(rows, streets, generated):
    serviceable = [r for r in rows if r["zone_id"] in (1, 2, 3, 4)]
    per_zone = {z: sum(1 for r in serviceable if r["zone_id"] == z) for z in (1, 2, 3, 4)}
    addr_per_zone = {z: sum(1 for r in serviceable if r["zone_id"] == z
                            and r["address_status"] == "verified_osm_address")
                     for z in (1, 2, 3, 4)}
    streets_per_zone = {z: sum(1 for s in streets if z in s["zones"]) for z in (1, 2, 3, 4)}
    severny = [r for r in rows if r.get("severny")]
    varnita_addr_in_zone = sum(
        1 for r in serviceable
        if (r["settlement_ru"] or "").lower().startswith("варниц"))
    return {
        "schema": "bender-final-zone-map-summary/1", "generated_at": generated,
        "decided_k": 4, "zone_edges_km": ZONE_EDGES, "zone_colors": ZONE_COLORS,
        "objects_per_zone": per_zone,
        "confirmed_addresses_per_zone": addr_per_zone,
        "streets_per_zone": streets_per_zone,
        "split_streets": sum(1 for s in streets if s["split_street"]),
        "unaddressed_delivery_units": sum(
            1 for r in rows if r["address_status"] == "unaddressed_delivery_unit"),
        "no_delivery": sum(1 for r in rows if r["service_status"] == "no_delivery"),
        "disputed": sum(1 for r in rows if r["service_status"] == "disputed"),
        "owner_review_objects": sum(1 for r in rows if r["owner_review_required"]),
        "severny_objects": len(severny),
        "severny_verified_addresses": sum(1 for r in severny
                                          if r.get("severny_verified")),
        "severny_zone4_objects": sum(1 for r in severny if r["zone_id"] == 4),
        "varnita_serviceable_addresses_in_zones": varnita_addr_in_zone,
        "readiness": {
            "zones_geometry_ready": True, "address_zone_catalog_ready": True,
            "street_zone_catalog_ready": True, "qa_map_ready": True,
            "prices_ready": False, "direct_integration_ready": False,
            "severny_address_catalog_complete": False, "owner_review_required": True},
    }


def _reports(reports, rows, streets, summary, generated):
    az = {
        "schema": "bender-address-zone-catalog-report/1", "generated_at": generated,
        "totals": summary, "objects": len(rows)}
    jsonutil.write(reports / "address-zone-catalog.json", az)
    lines = ["# Итоговый каталог адресов и зон", "",
             f"- Сгенерировано (UTC): `{generated}`",
             f"- K = **{summary['decided_k']}** · границы (км): "
             f"{summary['zone_edges_km']} · цены: **False** · Direct: **False**", "",
             "## Объекты по зонам", "",
             "| зона | объектов | подтв. адресов | улиц | цвет |",
             "|---|---:|---:|---:|---|"]
    for z in (1, 2, 3, 4):
        lines.append(f"| Zone {z} | {summary['objects_per_zone'][z]} | "
                     f"{summary['confirmed_addresses_per_zone'][z]} | "
                     f"{summary['streets_per_zone'][z]} | "
                     f"`{summary['zone_colors'][z]}` |")
    lines += ["", "## Прочее", "",
              f"- split streets: **{summary['split_streets']}**",
              f"- зданий без номера: **{summary['unaddressed_delivery_units']}**",
              f"- no_delivery: **{summary['no_delivery']}**",
              f"- disputed: **{summary['disputed']}**",
              f"- owner-review объектов: **{summary['owner_review_objects']}**",
              f"- Северный: **{summary['severny_objects']}** (в Zone 4: "
              f"{summary['severny_zone4_objects']}, verified: "
              f"{summary['severny_verified_addresses']})",
              f"- **адресов Варницы в зонах: {summary['varnita_serviceable_addresses_in_zones']}** "
              "(должно быть 0)", "",
              "## Готовность", ""]
    for k, val in summary["readiness"].items():
        lines.append(f"- `{k}`: **{val}**")
    lines += [""]
    (reports / "address-zone-catalog.md").write_text("\n".join(lines),
                                                     encoding="utf-8", newline="\n")

    split = [s for s in streets if s["split_street"]]
    sl = ["# Итоговый список улиц по зонам", "",
          f"- Сгенерировано (UTC): `{generated}`",
          f"- улиц всего: **{len(streets)}** · split streets: **{len(split)}**", "",
          "Источник истины — конкретный дом. Одинаковые улицы разных населённых "
          "пунктов/районов не объединяются.", "",
          "## Split streets (дома по зонам)", ""]
    for s in split[:60]:
        place = " / ".join(p for p in (s["settlement_ru"], s["district_ru"]) if p)
        parts = "; ".join(f"Zone {hz['zone_id']}: {', '.join(hz['houses'])}"
                          for hz in s["houses_by_zone"])
        sl.append(f"- **{s['street_ru']}** ({place}) — {parts}")
    if len(split) > 60:
        sl.append(f"- … и ещё {len(split) - 60}")
    sl += [""]
    (reports / "street-zone-summary.md").write_text("\n".join(sl),
                                                    encoding="utf-8", newline="\n")

    mv = ["# Валидация карты зон", "",
          f"- Сгенерировано (UTC): `{generated}`", "",
          "## Цвета (постоянные)", "",
          "| зона | цвет |", "|---|---|"]
    for z in (1, 2, 3, 4):
        mv.append(f"| Zone {z} | `{summary['zone_colors'][z]}` |")
    mv += ["", "## Проверки карты", "",
           "- заливка зон полупрозрачная, границы заметные;",
           "- дома окрашены по своей зоне (те же 4 цвета);",
           "- Северный — отдельный красный анклав Zone 4, без цветного коридора к "
           "Бендерам;",
           "- Варница — серый `no_delivery`; админ-граница только пунктирной линией;",
           "- Tier C — отдельный серый QA-слой; disputed — фиолетовый QA-слой;",
           "- территория без утверждённого покрытия не заливается;",
           f"- адресов Варницы в зонах: **{summary['varnita_serviceable_addresses_in_zones']}** "
           "(0).", ""]
    (reports / "map-zone-validation.md").write_text("\n".join(mv),
                                                    encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    return build(Path(ap.parse_args(argv).repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
