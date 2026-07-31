"""Zone-model audit (candidate branch) — Bender Delivery Zones.

Deterministic comparison of route-distance zone systems (K=4/5/6) over the
canonical 9,216 address grains. This is an ANALYTICAL candidate pipeline: it
never touches production zones, prices, releases or the routing graph.

Route metric = ``expected_km`` (the production origin-weighted OSRM road km that
reproduces the released zone_id). The city/outside decomposition needed for taxi
and hybrid economics is NOT available per address, so those metrics are only
computed for pure-city addresses (outside_city_km = 0) and left UNKNOWN for the
external service territories. Nothing is invented.

Owner-provided taxi economics are DERIVED ASSUMPTIONS, not a licensed tariff;
they are applied here for candidate analysis only and are never written back into
config/taxi-calibration.yml (which stays null and production-guarded).
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
POINTS = ROOT / "docs/data/final-address-zone-points.geojson"
BOUNDARY_CANDIDATES = ROOT / "config/boundary-candidates.yml"

OUT_DIR = ROOT / "data/interim"
FEATURES_CSV = OUT_DIR / "zone-model-address-features-v1.csv"
CANDIDATES_CSV = OUT_DIR / "zone-model-candidates-v1.csv"
ANCHORS_CSV = OUT_DIR / "external-tariff-boundary-anchors-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_route-model-summary-v1.json"

# Protected baseline (released K=4). Never altered here; reproduced for reference.
# Three interior thresholds define four zones; 9.692 km is the outer bound of the
# farthest zone (the maximum routed distance), not a fourth interior threshold.
BASELINE_EDGES = [2.424, 4.076, 5.577]
BASELINE_MAX_KM = 9.692
ORIGIN_LAT, ORIGIN_LON = 46.82388, 29.48313

CITY_SETTLEMENT = "Бендеры"
EXTERNAL_SETTLEMENTS = ("Гиска", "Парканы", "Протягайловка")

# Owner-provided operational evidence (DERIVED ASSUMPTION, not a confirmed tariff).
TAXI_MIN_FARE = 18.0
TAXI_CITY_RATE = 6.0
TAXI_OUTSIDE_RATE = 10.0
TAXI_FIXED_COMMISSION = 5.0
TAXI_PERCENT_KEPT = 0.65
EFFECTIVE_OUTSIDE_MULTIPLIER = 10.0 / 6.0  # 1.6666667 derived from 10/6, not a fact

BIN_WIDTH_KM = 0.05  # matches config/bands.yml cost-axis bin for the 1-D DP


def _round(value: float, digits: int = 3) -> float:
    return round(value + 0.0, digits)


def load_addresses() -> list[dict]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    points = json.loads(POINTS.read_text(encoding="utf-8"))["features"]
    coords_by_uid: dict[str, tuple[float, float]] = {}
    km_by_uid: dict[str, dict[str, float]] = {}
    for feature in points:
        props = feature["properties"]
        uid = props["uid"]
        lon, lat = feature["geometry"]["coordinates"]
        coords_by_uid[uid] = (lat, lon)
        km_by_uid[uid] = {
            "expected_km": props.get("expected_km"),
            "central_km": props.get("central_km"),
            "bam_km": props.get("bam_km"),
        }

    rows: list[dict] = []
    for entry in registry:
        uid = entry["uid"]
        if uid not in coords_by_uid or uid not in km_by_uid:
            raise ValueError(f"Registry uid missing from points geojson: {uid}")
        route_km = km_by_uid[uid]["expected_km"]
        if route_km is None:
            raise ValueError(f"Missing expected_km for {uid}")
        lat, lon = coords_by_uid[uid]
        settlement = entry["settlement_ru"]
        is_city = settlement == CITY_SETTLEMENT
        rows.append(
            {
                "uid": uid,
                "settlement": settlement,
                "district": entry.get("district_ru") or "",
                "street": entry["street_ru"],
                "house": entry["housenumber"],
                "lat": lat,
                "lon": lon,
                "route_km": float(route_km),
                "zone_id": int(entry["zone_id"]),
                "is_city": is_city,
                "service_status": entry["service_status"],
            }
        )
    rows.sort(key=lambda r: r["uid"])
    return rows


def zone_for(km: float, edges: list[float]) -> int:
    for index, edge in enumerate(edges):
        if km <= edge:
            return index + 1
    return len(edges) + 1


def thresholds_quantile(values: list[float], k: int) -> list[float]:
    ordered = sorted(values)
    n = len(ordered)
    edges = []
    for i in range(1, k):
        pos = i * n / k
        low = int(pos)
        if low >= n:
            low = n - 1
        edges.append(_round(ordered[low]))
    return _monotone(edges)


def _weighted_bins(values: list[float]) -> tuple[list[float], list[int]]:
    counts: dict[int, int] = defaultdict(int)
    for value in values:
        counts[int(round(value / BIN_WIDTH_KM))] += 1
    keys = sorted(counts)
    centers = [key * BIN_WIDTH_KM for key in keys]
    weights = [counts[key] for key in keys]
    return centers, weights


def thresholds_dp_optimal(values: list[float], k: int) -> list[float]:
    """Exact minimum weighted within-class SSE contiguous partition (Fisher/Jenks)."""
    centers, weights = _weighted_bins(values)
    m = len(centers)
    prefix_w = [0.0] * (m + 1)
    prefix_wx = [0.0] * (m + 1)
    prefix_wx2 = [0.0] * (m + 1)
    for i in range(m):
        prefix_w[i + 1] = prefix_w[i] + weights[i]
        prefix_wx[i + 1] = prefix_wx[i] + weights[i] * centers[i]
        prefix_wx2[i + 1] = prefix_wx2[i] + weights[i] * centers[i] * centers[i]

    def sse(a: int, b: int) -> float:  # bins [a, b)
        w = prefix_w[b] - prefix_w[a]
        if w <= 0:
            return 0.0
        wx = prefix_wx[b] - prefix_wx[a]
        wx2 = prefix_wx2[b] - prefix_wx2[a]
        return wx2 - wx * wx / w

    inf = float("inf")
    cost = [[inf] * (k + 1) for _ in range(m + 1)]
    split = [[0] * (k + 1) for _ in range(m + 1)]
    cost[0][0] = 0.0
    for i in range(1, m + 1):
        for j in range(1, min(k, i) + 1):
            for p in range(j - 1, i):
                candidate = cost[p][j - 1] + sse(p, i)
                if candidate < cost[i][j]:
                    cost[i][j] = candidate
                    split[i][j] = p
    boundaries = []
    i, j = m, k
    while j > 1:
        p = split[i][j]
        boundaries.append(p)
        i, j = p, j - 1
    boundaries.reverse()
    # Edge = midpoint between last center of a class and first center of the next.
    edges = []
    for p in boundaries:
        left = centers[p - 1]
        right = centers[p]
        edges.append(_round((left + right) / 2))
    return _monotone(edges)


def thresholds_kmeans(values: list[float], k: int) -> list[float]:
    ordered = sorted(values)
    n = len(ordered)
    centroids = [ordered[min(n - 1, int((i + 0.5) * n / k))] for i in range(k)]
    for _ in range(100):
        clusters: list[list[float]] = [[] for _ in range(k)]
        for value in ordered:
            best = min(range(k), key=lambda c: abs(value - centroids[c]))
            clusters[best].append(value)
        new = []
        for index, cluster in enumerate(clusters):
            new.append(sum(cluster) / len(cluster) if cluster else centroids[index])
        if all(abs(a - b) < 1e-9 for a, b in zip(new, centroids, strict=True)):
            centroids = new
            break
        centroids = new
    centroids.sort()
    edges = [_round((centroids[i] + centroids[i + 1]) / 2) for i in range(k - 1)]
    return _monotone(edges)


def _monotone(edges: list[float]) -> list[float]:
    out = []
    last = -1.0
    for edge in edges:
        if edge <= last:
            edge = _round(last + BIN_WIDTH_KM)
        out.append(edge)
        last = edge
    return out


def _percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        return 0.0
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def zone_stats(rows: list[dict], edges: list[float]) -> list[dict]:
    members: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        members[zone_for(row["route_km"], edges)].append(row)
    total = len(rows)
    stats = []
    bounds = [0.0, *edges, None]
    for zone in range(1, len(edges) + 2):
        group = members.get(zone, [])
        kms = sorted(r["route_km"] for r in group)
        stats.append(
            {
                "zone_id": zone,
                "lower_bound": bounds[zone - 1],
                "upper_bound": bounds[zone],
                "address_count": len(group),
                "population_share": _round(len(group) / total, 4),
                "min_route_km": _round(kms[0]) if kms else None,
                "median_route_km": _round(_percentile(kms, 0.5)) if kms else None,
                "p90_route_km": _round(_percentile(kms, 0.9)) if kms else None,
                "max_route_km": _round(kms[-1]) if kms else None,
            }
        )
    return stats


def boundary_instability(rows: list[dict], edges: list[float], pct: float) -> int:
    flips = 0
    for row in rows:
        base = zone_for(row["route_km"], edges)
        up = zone_for(row["route_km"] * (1 + pct), edges)
        down = zone_for(row["route_km"] * (1 - pct), edges)
        if up != base or down != base:
            flips += 1
    return flips


def build_models(rows: list[dict]) -> tuple[list[dict], dict]:
    values = [row["route_km"] for row in rows]
    models: list[tuple[str, str, list[float]]] = [
        ("BASELINE_4", "production_released", BASELINE_EDGES),
    ]
    method_funcs = {
        "quantile": thresholds_quantile,
        "kmeans": thresholds_kmeans,
        "dp_optimal_jenks": thresholds_dp_optimal,
    }
    for k in (4, 5, 6):
        for method, func in method_funcs.items():
            models.append((f"K{k}R_{method}", method, func(values, k)))

    candidate_rows: list[dict] = []
    summary: dict = {"models": {}}
    for model_id, method, edges in models:
        k = len(edges) + 1
        stats = zone_stats(rows, edges)
        instability = {
            f"flip_pct_{int(p * 100)}": boundary_instability(rows, edges, p)
            for p in (0.03, 0.05, 0.10)
        }
        for stat in stats:
            candidate_rows.append(
                {
                    "model_id": model_id,
                    "metric": "route_km",
                    "method": method,
                    "k": k,
                    "zone_id": stat["zone_id"],
                    "lower_bound": "" if stat["lower_bound"] is None else stat["lower_bound"],
                    "upper_bound": "" if stat["upper_bound"] is None else stat["upper_bound"],
                    "address_count": stat["address_count"],
                    "population_share": stat["population_share"],
                    "median_route_km": stat["median_route_km"],
                    "median_effective_km": "PENDING_COMMIT2",
                    "median_taxi_reference": "PENDING_COMMIT2",
                    "candidate_delivery_fee_rub": "PENDING_COMMIT2",
                    "client_median_saving_rub": "PENDING_COMMIT2",
                    "driver_median_gap_rub": "PENDING_COMMIT2",
                    "boundary_instability_count": instability["flip_pct_5"],
                    "confidence": "HIGH" if model_id == "BASELINE_4" else "CANDIDATE",
                    "notes": "route_km partition; economics pending commit 2",
                }
            )
        summary["models"][model_id] = {
            "k": k,
            "method": method,
            "edges": edges,
            "zone_counts": [s["address_count"] for s in stats],
            "population_share": [s["population_share"] for s in stats],
            "min_share": min(s["population_share"] for s in stats),
            "max_share": max(s["population_share"] for s in stats),
            "instability": instability,
        }
    return candidate_rows, summary


def taxi_reference_a(in_city_km: float, outside_km: float) -> float:
    return max(TAXI_MIN_FARE, TAXI_CITY_RATE * in_city_km + TAXI_OUTSIDE_RATE * outside_km)


def taxi_reference_b(in_city_km: float, outside_km: float) -> float:
    return (
        TAXI_MIN_FARE
        + TAXI_CITY_RATE * max(0.0, in_city_km - 3.0)
        + TAXI_OUTSIDE_RATE * outside_km
    )


def write_features(rows: list[dict]) -> None:
    header = [
        "address_id", "territory", "district", "street", "house_number", "lat", "lon",
        "route_km", "route_duration_min", "route_metric_status", "in_city_km",
        "outside_city_km", "outside_split_status", "boundary_anchor_id",
        "effective_km_1667", "taxi_model_a_reference_rub", "taxi_model_b_reference_rub",
        "driver_take_fixed_a_rub", "driver_take_percent_a_rub",
        "driver_best_taxi_take_a_rub", "current_zone_id", "data_confidence",
        "evidence_notes",
    ]
    with FEATURES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in sorted(rows, key=lambda r: r["uid"]):
            route_km = row["route_km"]
            if row["is_city"]:
                in_city = _round(route_km)
                outside = 0.0
                split_status = "CITY_ALL_IN"
                effective = _round(route_km)
                ref_a = _round(taxi_reference_a(route_km, 0.0), 2)
                ref_b = _round(taxi_reference_b(route_km, 0.0), 2)
                fixed = _round(max(0.0, ref_a - TAXI_FIXED_COMMISSION), 2)
                percent = _round(TAXI_PERCENT_KEPT * ref_a, 2)
                best = _round(max(fixed, percent), 2)
                confidence = "CITY_OWNER_ASSUMPTION"
                notes = "outside_city_km=0 by city doctrine; taxi = owner assumption"
            else:
                in_city = ""
                outside = ""
                split_status = "OUTSIDE_SPLIT_UNKNOWN"
                effective = ""
                ref_a = ref_b = fixed = percent = best = ""
                confidence = "EXTERNAL_SPLIT_UNKNOWN"
                notes = "external territory; in/out split unproven; see commit 2 brackets"
            writer.writerow([
                row["uid"], row["settlement"], row["district"], row["street"],
                row["house"], _round(row["lat"], 6), _round(row["lon"], 6),
                _round(route_km), "", "expected_km_osrm", in_city, outside,
                split_status, "", effective, ref_a, ref_b, fixed, percent, best,
                row["zone_id"], confidence, notes,
            ])


def write_candidates(candidate_rows: list[dict]) -> None:
    header = [
        "model_id", "metric", "method", "k", "zone_id", "lower_bound", "upper_bound",
        "address_count", "population_share", "median_route_km", "median_effective_km",
        "median_taxi_reference", "candidate_delivery_fee_rub", "client_median_saving_rub",
        "driver_median_gap_rub", "boundary_instability_count", "confidence", "notes",
    ]
    with CANDIDATES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidate_rows)


def write_anchors() -> list[dict]:
    text = BOUNDARY_CANDIDATES.read_text(encoding="utf-8")
    admin_ids = [line.split("id:")[1].strip() for line in text.splitlines() if "- id:" in line]
    anchors = [
        {
            "anchor_id": "PARKANY_KOTOVSKOGO_GAI_POST",
            "territory": "Парканы",
            "anchor_name": "Пост ГАИ на ул. Котовского (из Бендер в сторону Паркан)",
            "lat": "", "lon": "",
            "source_type": "OWNER_BRIEF_ONLY",
            "source_evidence": "owner-provided candidate boundary; NOT present in OSM/GIS data",
            "route_coverage_count": 0,
            "alternative_entry_exists": "UNKNOWN",
            "confidence": "UNPROVEN",
            "owner_confirmation_required": "True",
            "notes": "UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION — no coordinates invented",
        },
        {
            "anchor_id": "GISKA_EXTERNAL_ENTRY",
            "territory": "Гиска",
            "anchor_name": "Candidate Гиска entry corridor",
            "lat": "", "lon": "",
            "source_type": "NOT_ESTABLISHED",
            "source_evidence": "no proven single boundary anchor in data",
            "route_coverage_count": 0,
            "alternative_entry_exists": "UNKNOWN",
            "confidence": "UNPROVEN",
            "owner_confirmation_required": "True",
            "notes": "do not copy Parkany boundary; separate corridor evidence required",
        },
        {
            "anchor_id": "PROTYAGAILOVKA_EXTERNAL_ENTRY",
            "territory": "Протягайловка",
            "anchor_name": "Candidate Протягайловка entry corridor",
            "lat": "", "lon": "",
            "source_type": "NOT_ESTABLISHED",
            "source_evidence": "multiple corridor files exist but no proven single tariff boundary",
            "route_coverage_count": 0,
            "alternative_entry_exists": "UNKNOWN",
            "confidence": "UNPROVEN",
            "owner_confirmation_required": "True",
            "notes": "several corridors; boundary + outside length require evidence",
        },
        {
            "anchor_id": "SEVERNY_BOUNDARY",
            "territory": "Северный",
            "anchor_name": "Северный classification boundary",
            "lat": "", "lon": "",
            "source_type": "EVIDENCE_COLLECTION_ONLY",
            "source_evidence": "not auto-classified as Varnita, city or external",
            "route_coverage_count": 0,
            "alternative_entry_exists": "UNKNOWN",
            "confidence": "UNPROVEN",
            "owner_confirmation_required": "True",
            "notes": "OWNER_BOUNDARY_DECISION_REQUIRED",
        },
    ]
    header = [
        "anchor_id", "territory", "anchor_name", "lat", "lon", "source_type",
        "source_evidence", "route_coverage_count", "alternative_entry_exists",
        "confidence", "owner_confirmation_required", "notes",
    ]
    with ANCHORS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(anchors)
    return admin_ids


def main() -> None:
    rows = load_addresses()
    assert len(rows) == 9216, f"expected 9216 addresses, got {len(rows)}"
    assert all(r["settlement"] != "Варница" for r in rows), "Varnita must not be present"

    baseline_match = sum(
        1 for r in rows if zone_for(r["route_km"], BASELINE_EDGES) == r["zone_id"]
    )
    territory_counts = Counter(r["settlement"] for r in rows)
    city = [r for r in rows if r["is_city"]]
    external = [r for r in rows if not r["is_city"]]

    candidate_rows, summary = build_models(rows)
    write_features(rows)
    write_candidates(candidate_rows)
    admin_ids = write_anchors()

    kms = sorted(r["route_km"] for r in rows)
    summary["readiness"] = {
        "canonical_population": len(rows),
        "route_km_field": "expected_km",
        "route_km_coverage": len(rows),
        "baseline_zone_reproduction": baseline_match,
        "baseline_edges": BASELINE_EDGES,
        "baseline_max_km": BASELINE_MAX_KM,
        "registry_zone_counts": dict(sorted(Counter(r["zone_id"] for r in rows).items())),
        "route_km_min": _round(kms[0]),
        "route_km_median": _round(_percentile(kms, 0.5)),
        "route_km_p90": _round(_percentile(kms, 0.9)),
        "route_km_max": _round(kms[-1]),
        "territory_counts": dict(territory_counts),
        "city_addresses": len(city),
        "external_addresses": len(external),
        "outside_split_coverage": 0,
        "boundary_anchors_proven": 0,
        "admin_boundary_relation_ids": admin_ids,
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary["readiness"], ensure_ascii=False, indent=2))
    for model_id, info in summary["models"].items():
        print(model_id, "edges=", info["edges"], "counts=", info["zone_counts"])


if __name__ == "__main__":
    main()
