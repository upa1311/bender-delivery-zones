"""Final K=4 / Scenario A catalog: address, street and zone-map deliverables."""

from __future__ import annotations

import csv
import json

from shapely.geometry import shape

ZONE_EDGES = [2.424, 4.076, 5.577, 9.692]
ZONE_COLORS = {"1": "#2a9d3f", "2": "#f2c500", "3": "#f07f14", "4": "#d62828"}


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _catalog(repo_root):
    text = (repo_root / "docs/data/final-address-zone-catalog.csv").read_text("utf-8")
    return list(csv.DictReader(text.splitlines()))


def _streets(repo_root):
    return _json(repo_root, "docs/data/final-street-zone-catalog.json")["streets"]


def _summary(repo_root):
    return _json(repo_root, "docs/data/final-zone-map-summary.json")


# --- zones and edges --------------------------------------------------------

def test_every_serviceable_object_has_a_zone_1_to_4(repo_root):
    for r in _catalog(repo_root):
        if r["service_status"] in ("standard", "low_density"):
            assert r["zone_id"] in ("1", "2", "3", "4"), r["uid"]


def test_excluded_objects_have_no_zone(repo_root):
    for r in _catalog(repo_root):
        if r["service_status"] in ("disputed", "no_delivery", "excluded"):
            assert r["zone_id"] in ("", None), \
                f"{r['uid']} is {r['service_status']} but has a zone"


def test_k_stays_4_and_edges_unchanged(repo_root):
    s = _summary(repo_root)
    assert s["decided_k"] == 4
    assert s["zone_edges_km"] == ZONE_EDGES
    metrics = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert metrics["candidates"]["4"]["upper_edges_km"] == ZONE_EDGES
    zone_ids = {p["properties"]["zone_id"]
                for p in _json(repo_root, "docs/data/final-zone-polygons.geojson")
                ["features"]}
    assert 5 not in zone_ids, "no Zone 5 may exist"


def test_no_object_is_in_two_zones(repo_root):
    by_uid = {}
    for r in _catalog(repo_root):
        by_uid.setdefault(r["uid"], set()).add(r["zone_id"])
    assert all(len(z) == 1 for z in by_uid.values())


def test_one_canonical_address_maps_to_one_zone(repo_root):
    by_key = {}
    for r in _catalog(repo_root):
        if r["canonical_address_key"] and r["zone_id"] in ("1", "2", "3", "4"):
            by_key.setdefault(r["canonical_address_key"], set()).add(r["zone_id"])
    offenders = {k: z for k, z in by_key.items() if len(z) > 1}
    assert not offenders, f"canonical addresses spanning zones: {list(offenders)[:3]}"


# --- disputed / exclusions --------------------------------------------------

def test_disputed_addresses_are_not_client_ready(repo_root):
    for r in _catalog(repo_root):
        if r["service_status"] == "disputed":
            assert r["zone_id"] in ("", None)
            assert r["direct_export_eligible"] == "False"


def test_varnita_has_zero_serviceable_addresses(repo_root):
    for r in _catalog(repo_root):
        if r["zone_id"] in ("1", "2", "3", "4"):
            assert not (r["settlement_ru"] or "").lower().startswith("варниц")
    assert _summary(repo_root)["varnita_serviceable_addresses_in_zones"] == 0


# --- Северный ---------------------------------------------------------------

def test_severny_settlement_and_all_in_zone_4(repo_root):
    sev = [r for r in _catalog(repo_root) if r["district_ru"] == "Северный"]
    assert len(sev) == 57
    for r in sev:
        assert r["settlement_ru"] == "Бендеры"
        assert r["zone_id"] == "4"
        assert r["owner_review_required"] == "True"


def test_only_seven_severny_verified_addresses(repo_root):
    sev = [r for r in _catalog(repo_root) if r["district_ru"] == "Северный"]
    verified = [r for r in sev if r["address_status"] == "verified_osm_address"]
    unaddressed = [r for r in sev if r["address_status"] == "unaddressed_delivery_unit"]
    assert len(verified) == 7
    assert len(unaddressed) == 50
    for r in unaddressed:
        assert not r["housenumber"], "unaddressed unit must not have a house number"


def test_severny_house_numbers_are_not_synthesized(repo_root):
    hns = {r["housenumber"] for r in _catalog(repo_root)
           if r["district_ru"] == "Северный" and r["housenumber"]}
    assert len(hns) <= 7
    assert not {str(n) for n in range(1, 106)} <= hns


# --- street catalog ---------------------------------------------------------

def test_same_street_in_different_settlements_not_merged(repo_root):
    keys = [(s["settlement_ru"], s["district_ru"], s["street_ru"])
            for s in _streets(repo_root)]
    assert len(keys) == len(set(keys))
    lenin = [s for s in _streets(repo_root) if "Ленина" in (s["street_ru"] or "")]
    settlements = {s["settlement_ru"] for s in lenin}
    assert len(settlements) >= 2, "улица Ленина must stay split across settlements"


def test_split_streets_list_exact_houses_per_zone(repo_root):
    split = [s for s in _streets(repo_root) if s["split_street"]]
    assert split
    for s in split:
        zones = [hz["zone_id"] for hz in s["houses_by_zone"]]
        assert len(zones) == len(set(zones)) >= 2
        seen = set()
        for hz in s["houses_by_zone"]:
            assert hz["houses"], "each zone in a split street lists its exact houses"
            for h in hz["houses"]:
                assert h not in seen, "a house cannot be in two zones of one street"
                seen.add(h)


def test_letter_and_fraction_houses_are_not_ranged(repo_root):
    """Every catalog house number must appear verbatim in the source data.

    This proves no numbers were fabricated by compressing "2, 4, 6" into "2-6":
    any hyphen (e.g. the OSM value "16-а") is only allowed because it exists
    verbatim in the source, not because the catalog invented a range.
    """
    source = {r["housenumber"] for r in csv.DictReader(
        (repo_root / "docs/data/delivery-units.csv").read_text("utf-8").splitlines())
        if r["housenumber"]}
    source |= {r["housenumber"] for r in csv.DictReader(
        (repo_root / "docs/data/severny-delivery-units.csv").read_text("utf-8").splitlines())
        if r["housenumber"]}
    found_special = False
    for s in _streets(repo_root):
        for hz in s["houses_by_zone"]:
            for h in hz["houses"]:
                assert h in source, f"house {h!r} is not a verbatim OSM value"
                if "/" in h or any(c.isalpha() for c in h):
                    found_special = True
    assert found_special, "letter/fraction house numbers must be preserved verbatim"


def test_partial_street_is_not_assigned_one_zone_for_whole(repo_root):
    for s in _streets(repo_root):
        if len(s["zones"]) > 1:
            assert s["split_street"] is True


# --- map colours + summary --------------------------------------------------

def test_zone_polygons_use_four_distinct_colours(repo_root):
    fc = _json(repo_root, "docs/data/final-zone-polygons.geojson")
    colors = {f["properties"]["color"] for f in fc["features"]}
    assert colors == set(ZONE_COLORS.values())
    for f in fc["features"]:
        assert f["properties"]["color"] == ZONE_COLORS[str(f["properties"]["zone_id"])]


def test_severny_is_a_separate_zone4_component(repo_root):
    fc = _json(repo_root, "docs/data/final-zone-polygons.geojson")
    comps = [f["properties"]["component"] for f in fc["features"]]
    assert "severny_enclave" in comps
    sev = next(f for f in fc["features"]
               if f["properties"]["component"] == "severny_enclave")
    assert sev["properties"]["zone_id"] == 4
    main4 = next(f for f in fc["features"]
                 if f["properties"]["component"] == "bender_main"
                 and f["properties"]["zone_id"] == 4)
    assert not shape(sev["geometry"]).intersects(shape(main4["geometry"])), \
        "Северный must not be joined to main Bender by a coloured corridor"


def test_catalog_js_uses_the_four_zone_colours(repo_root):
    js = (repo_root / "docs/catalog.js").read_text(encoding="utf-8")
    for c in ZONE_COLORS.values():
        assert c in js, c
    assert "Дом не подтверждён" in js
    assert "Стоимость доставки не отображается" in js  # no prices shown


def test_readiness_status_is_published(repo_root):
    r = _summary(repo_root)["readiness"]
    assert r["zones_geometry_ready"] is True
    assert r["address_zone_catalog_ready"] is True
    assert r["street_zone_catalog_ready"] is True
    assert r["qa_map_ready"] is True
    assert r["prices_ready"] is False
    assert r["direct_integration_ready"] is False
    assert r["severny_address_catalog_complete"] is False
    assert r["owner_review_required"] is True


def test_no_prices_or_direct_anywhere(repo_root):
    for name in ("final-address-zone-catalog.json", "final-zone-map-summary.json"):
        doc = _json(repo_root, f"docs/data/{name}")
        blob = json.dumps(doc, ensure_ascii=False).lower()
        assert "delivery_fee" not in blob and "courier_payout" not in blob


def test_reports_exist(repo_root):
    for name in ("address-zone-catalog.md", "address-zone-catalog.json",
                 "street-zone-summary.md", "map-zone-validation.md"):
        assert (repo_root / "reports/final" / name).exists(), name
