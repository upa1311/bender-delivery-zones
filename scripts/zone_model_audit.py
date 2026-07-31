"""Zone-model audit (candidate branch) — Bender Delivery Zones.

Deterministic decision-layer analysis over the canonical 9,216 address grains.
This is an ANALYTICAL candidate pipeline: it never touches production zones,
prices, releases or the routing graph.

Two model families are kept strictly separate:

  * FULL-POPULATION DIAGNOSTICS (BASELINE_4, K4R/K5R/K6R over all 9,216) — a
    route-distance description only, NOT a deployable tariff system, because
    4,350 external addresses have OUTSIDE_SPLIT_UNKNOWN.
  * CITY DEPLOYABLE CANDIDATES (CITY_K4R/K5R/K6R over the 4,866 pure-city
    addresses, outside_km = 0) — the models the owner actually decides between.

Route metric = ``expected_km`` (the production origin-weighted OSRM road km).
Nothing is invented; missing splits/boundaries are marked, not filled.
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
ROUTE_CONTROLS = ROOT / "docs/data/manual-yandex-route-controls.csv"
MEASUREMENTS = ROOT / "docs/data/manual-yandex-measurements.csv"

OUT_DIR = ROOT / "data/interim"
FEATURES_CSV = OUT_DIR / "zone-model-address-features-v1.csv"
CANDIDATES_CSV = OUT_DIR / "zone-model-candidates-v1.csv"
ANCHORS_CSV = OUT_DIR / "external-tariff-boundary-anchors-v1.csv"
MISMATCH_CSV = OUT_DIR / "zone-baseline-reproduction-mismatches-v1.csv"
MANUAL_CSV = OUT_DIR / "zone-model-manual-control-validation-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_route-model-summary-v1.json"

# Protected baseline (released K=4): three interior thresholds → four zones.
# 9.692 km is the outer bound of the far zone (max routed km), not a threshold.
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
EFFECTIVE_OUTSIDE_MULTIPLIER = 10.0 / 6.0

BIN_WIDTH_KM = 0.05
ROUNDING_STEPS_KM = [0.1, 0.25, 0.5]


def _round(value: float, digits: int = 3) -> float:
    return round(value + 0.0, digits)


def load_addresses() -> list[dict]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    points = json.loads(POINTS.read_text(encoding="utf-8"))["features"]
    coords_by_uid: dict[str, tuple[float, float]] = {}
    km_by_uid: dict[str, float] = {}
    for feature in points:
        props = feature["properties"]
        uid = props["uid"]
        lon, lat = feature["geometry"]["coordinates"]
        coords_by_uid[uid] = (lat, lon)
        km_by_uid[uid] = props.get("expected_km")

    rows: list[dict] = []
    for entry in registry:
        uid = entry["uid"]
        if uid not in coords_by_uid or km_by_uid.get(uid) is None:
            raise ValueError(f"Registry uid missing coords/km: {uid}")
        lat, lon = coords_by_uid[uid]
        settlement = entry["settlement_ru"]
        rows.append(
            {
                "uid": uid,
                "settlement": settlement,
                "district": entry.get("district_ru") or "",
                "street": entry["street_ru"],
                "house": entry["housenumber"],
                "lat": lat,
                "lon": lon,
                "route_km": float(km_by_uid[uid]),
                "zone_id": int(entry["zone_id"]),
                "is_city": settlement == CITY_SETTLEMENT,
                "service_status": entry["service_status"],
            }
        )
    rows.sort(key=lambda r: r["uid"])
    return rows


def zone_for(km: float, edges: list[float]) -> int:
    """Zone by the <= convention (threshold belongs to the lower zone)."""
    for index, edge in enumerate(edges):
        if km <= edge:
            return index + 1
    return len(edges) + 1


def zone_for_released(km: float, edges: list[float]) -> int:
    """Released convention: a value exactly on a threshold falls in the UPPER zone."""
    for index, edge in enumerate(edges):
        if km < edge:
            return index + 1
    return len(edges) + 1


# ----------------------- partition methods -----------------------

def thresholds_quantile(values: list[float], k: int) -> list[float]:
    ordered = sorted(values)
    n = len(ordered)
    edges = []
    for i in range(1, k):
        pos = i * n / k
        low = min(int(pos), n - 1)
        edges.append(_round(ordered[low]))
    return _monotone(edges)


def _weighted_bins(values: list[float]) -> tuple[list[float], list[int]]:
    counts: dict[int, int] = defaultdict(int)
    for value in values:
        counts[int(round(value / BIN_WIDTH_KM))] += 1
    keys = sorted(counts)
    return [key * BIN_WIDTH_KM for key in keys], [counts[key] for key in keys]


def _bin_prefixes(centers, weights):
    m = len(centers)
    pw = [0.0] * (m + 1)
    pwx = [0.0] * (m + 1)
    pwx2 = [0.0] * (m + 1)
    for i in range(m):
        pw[i + 1] = pw[i] + weights[i]
        pwx[i + 1] = pwx[i] + weights[i] * centers[i]
        pwx2[i + 1] = pwx2[i] + weights[i] * centers[i] * centers[i]
    return pw, pwx, pwx2


def thresholds_dp_optimal(values: list[float], k: int) -> list[float]:
    """Exact minimum weighted within-class SSE contiguous partition (Fisher/Jenks)."""
    centers, weights = _weighted_bins(values)
    m = len(centers)
    pw, pwx, pwx2 = _bin_prefixes(centers, weights)

    def sse(a: int, b: int) -> float:
        w = pw[b] - pw[a]
        if w <= 0:
            return 0.0
        wx = pwx[b] - pwx[a]
        return (pwx2[b] - pwx2[a]) - wx * wx / w

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
    return _boundaries_to_edges(centers, _backtrack(split, m, k))


def _backtrack(split, m, k) -> list[int]:
    boundaries = []
    i, j = m, k
    while j > 1:
        p = split[i][j]
        boundaries.append(p)
        i, j = p, j - 1
    boundaries.reverse()
    return boundaries


def _boundaries_to_edges(centers, boundaries) -> list[float]:
    edges = [_round((centers[p - 1] + centers[p]) / 2) for p in boundaries]
    return _monotone(edges)


def thresholds_business_constrained(values: list[float], k: int) -> tuple[list[float], str]:
    """Constrained contiguous partition: SSE + a small near-cut density penalty,
    subject to per-zone share in [min_share, 0.40] and width >= 0.5 km. min_share
    relaxes 0.12 -> 0.10 -> 0.05 until feasible; the used floor is reported.
    """
    centers, weights = _weighted_bins(values)
    m = len(centers)
    total = sum(weights)
    pw, pwx, pwx2 = _bin_prefixes(centers, weights)
    max_share, min_width, lam = 0.40, 0.5, 0.02

    def sse(a, b):
        w = pw[b] - pw[a]
        if w <= 0:
            return 0.0
        wx = pwx[b] - pwx[a]
        return (pwx2[b] - pwx2[a]) - wx * wx / w

    def feasible(a, b, min_share):
        w = pw[b] - pw[a]
        share = w / total
        width = centers[b - 1] - centers[a]
        return min_share <= share <= max_share and width >= min_width - 1e-9

    for min_share in (0.12, 0.10, 0.05):
        inf = float("inf")
        cost = [[inf] * (k + 1) for _ in range(m + 1)]
        split = [[0] * (k + 1) for _ in range(m + 1)]
        cost[0][0] = 0.0
        for i in range(1, m + 1):
            for j in range(1, min(k, i) + 1):
                for p in range(j - 1, i):
                    if cost[p][j - 1] == inf or not feasible(p, i, min_share):
                        continue
                    cut_pen = lam * (weights[p] + weights[p - 1]) if p > 0 else 0.0
                    candidate = cost[p][j - 1] + sse(p, i) + cut_pen
                    if candidate < cost[i][j]:
                        cost[i][j] = candidate
                        split[i][j] = p
        if cost[m][k] < inf:
            edges = _boundaries_to_edges(centers, _backtrack(split, m, k))
            return edges, f"business_constrained(min_share={min_share})"
    # fall back to unconstrained DP if even 5% infeasible
    return thresholds_dp_optimal(values, k), "business_constrained(FELL_BACK_TO_DP)"


def thresholds_kmeans(values: list[float], k: int) -> list[float]:
    ordered = sorted(values)
    n = len(ordered)
    centroids = [ordered[min(n - 1, int((i + 0.5) * n / k))] for i in range(k)]
    for _ in range(100):
        clusters: list[list[float]] = [[] for _ in range(k)]
        for value in ordered:
            best = min(range(k), key=lambda c: abs(value - centroids[c]))
            clusters[best].append(value)
        new = [sum(cl) / len(cl) if cl else centroids[i] for i, cl in enumerate(clusters)]
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


def zone_members(rows: list[dict], edges: list[float]) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(len(edges) + 1)]
    for row in rows:
        buckets[zone_for(row["route_km"], edges) - 1].append(row)
    return buckets


def rounding_variants(edges: list[float]) -> dict:
    return {str(step): [_round(round(e / step) * step) for e in edges]
            for step in ROUNDING_STEPS_KM}


def boundary_instability(rows: list[dict], edges: list[float], pct: float) -> int:
    flips = 0
    for row in rows:
        base = zone_for(row["route_km"], edges)
        if (zone_for(row["route_km"] * (1 + pct), edges) != base
                or zone_for(row["route_km"] * (1 - pct), edges) != base):
            flips += 1
    return flips


# ----------------------- baseline mismatch audit -----------------------

def baseline_mismatches(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        rc = zone_for(row["route_km"], BASELINE_EDGES)
        if rc == row["zone_id"]:
            continue
        km = row["route_km"]
        nearest = min(BASELINE_EDGES, key=lambda e: abs(km - e))
        on_edge = abs(km - nearest) < 1e-9
        released = zone_for_released(km, BASELINE_EDGES)
        reason = ("threshold_inclusivity" if on_edge and released == row["zone_id"]
                  else "unresolved")
        out.append({
            "address_id": row["uid"], "territory": row["settlement"],
            "district": row["district"], "street": row["street"],
            "house_number": row["house"], "expected_km": _round(km),
            "registry_zone_id": row["zone_id"], "recomputed_zone_id": rc,
            "nearest_threshold_km": _round(nearest),
            "distance_to_threshold_km": _round(km - nearest),
            "source_file": "releases/bender-zones-v1.1/address-registry.json",
            "reason": reason,
            "status": "explained_by_inclusivity_convention"
            if reason == "threshold_inclusivity" else "UNRESOLVED",
        })
    out.sort(key=lambda r: r["address_id"])
    return out


def write_mismatches(mismatches: list[dict]) -> None:
    header = ["address_id", "territory", "district", "street", "house_number",
              "expected_km", "registry_zone_id", "recomputed_zone_id",
              "nearest_threshold_km", "distance_to_threshold_km", "source_file",
              "reason", "status"]
    with MISMATCH_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(mismatches)


# ----------------------- manual-control validation -----------------------

def load_manual_controls(reg_by_uid: dict[str, dict]) -> list[dict]:
    controls = {row["control_id"]: row
                for row in _read_csv(ROUTE_CONTROLS)}
    out = []
    for meas in _read_csv(MEASUREMENTS):
        cid = meas["control_id"]
        yk = meas.get("yandex_fastest_distance_km")
        ctrl = controls.get(cid)
        if not ctrl or yk in (None, "", "null"):
            continue
        uid = ctrl["uid"]
        if uid not in reg_by_uid:
            continue  # control address is outside the 9,216 population
        reg = reg_by_uid[uid]
        out.append({
            "control_id": cid, "uid": uid, "territory": reg["settlement"],
            "is_city": reg["is_city"],
            "router_km": reg["route_km"], "yandex_km": float(yk),
        })
    out.sort(key=lambda r: r["control_id"])
    return out


def manual_validation_rows(controls: list[dict], model_defs: list[tuple]) -> list[dict]:
    rows = []
    for model_id, edges, scope in model_defs:
        pool = [c for c in controls if (c["is_city"] if scope == "CITY" else True)]
        for c in pool:
            rz = zone_for(c["router_km"], edges)
            yz = zone_for(c["yandex_km"], edges)
            near = min(abs(c["router_km"] - e) for e in edges)
            delta = abs(rz - yz)
            rows.append({
                "model_id": model_id, "control_id": c["control_id"], "uid": c["uid"],
                "territory": c["territory"], "router_km": _round(c["router_km"]),
                "yandex_km": _round(c["yandex_km"]), "router_zone": rz,
                "yandex_zone": yz, "zone_delta": delta,
                "near_threshold_km": _round(near),
                "flip_type": ("same_zone" if delta == 0 else
                              "one_zone_flip" if delta == 1 else "multi_zone_flip"),
            })
    return rows


def write_manual_validation(rows: list[dict]) -> None:
    header = ["model_id", "control_id", "uid", "territory", "router_km", "yandex_km",
              "router_zone", "yandex_zone", "zone_delta", "near_threshold_km",
              "flip_type"]
    with MANUAL_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def manual_summary(rows: list[dict]) -> dict:
    by_model: dict[str, dict] = {}
    for r in rows:
        m = by_model.setdefault(r["model_id"], {
            "controls": 0, "same_zone": 0, "one_zone_flip": 0, "multi_zone_flip": 0,
            "within_50m": 0, "within_100m": 0, "within_250m": 0,
            "by_territory": defaultdict(int), "flip_ids": []})
        m["controls"] += 1
        m[r["flip_type"]] += 1
        if r["near_threshold_km"] <= 0.05:
            m["within_50m"] += 1
        if r["near_threshold_km"] <= 0.10:
            m["within_100m"] += 1
        if r["near_threshold_km"] <= 0.25:
            m["within_250m"] += 1
        m["by_territory"][r["territory"]] += 1
        if r["flip_type"] != "same_zone":
            m["flip_ids"].append(r["control_id"])
    for m in by_model.values():
        m["by_territory"] = dict(m["by_territory"])
    return by_model


# ----------------------- model building -----------------------

def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _zone_row(model_id, method, k, metric, scope, zi, lower, upper,
              members, all_rows, city_rows_all) -> dict:
    kms = sorted(r["route_km"] for r in members)
    all_n = len(all_rows)
    city_n = len(city_rows_all)
    city_members = sum(1 for r in members if r["is_city"])
    return {
        "model_id": model_id, "metric": metric, "method": method, "k": k,
        "zone_id": zi, "lower_bound": _round(lower),
        "upper_bound": "" if upper is None else _round(upper),
        "all_address_count": len(members) if scope == "FULL" else "",
        "all_population_share": _round(len(members) / all_n, 4) if scope == "FULL" else "",
        "city_address_count": city_members if scope == "FULL" else len(members),
        "city_population_share": _round(
            (city_members if scope == "FULL" else len(members)) / city_n, 4),
        "economic_scope": "DIAGNOSTIC_ROUTE_ONLY" if scope == "FULL" else "CITY_DEPLOYABLE",
        "median_route_km": _round(_percentile(kms, 0.5)) if kms else "",
        "median_effective_km": "PENDING_ECON" if scope == "CITY" else "",
        "median_taxi_reference": "PENDING_ECON" if scope == "CITY" else "",
        "candidate_delivery_fee_rub": "PENDING_ECON" if scope == "CITY" else "",
        "client_median_saving_rub": "PENDING_ECON" if scope == "CITY" else "",
        "driver_median_gap_rub": "PENDING_ECON" if scope == "CITY" else "",
        "boundary_instability_count": "",
        "confidence": "DIAGNOSTIC" if scope == "FULL" else "CITY_CANDIDATE",
        "notes": "",
    }


CANDIDATE_HEADER = [
    "model_id", "metric", "method", "k", "zone_id", "lower_bound", "upper_bound",
    "all_address_count", "all_population_share", "city_address_count",
    "city_population_share", "economic_scope", "median_route_km",
    "median_effective_km", "median_taxi_reference", "candidate_delivery_fee_rub",
    "client_median_saving_rub", "driver_median_gap_rub", "boundary_instability_count",
    "confidence", "notes",
]


def build_all_models(rows: list[dict]) -> tuple[list[dict], dict]:
    city = [r for r in rows if r["is_city"]]
    all_values = [r["route_km"] for r in rows]
    city_values = [r["route_km"] for r in city]
    method_funcs = {
        "quantile": thresholds_quantile,
        "kmeans": thresholds_kmeans,
        "dp_optimal_jenks": thresholds_dp_optimal,
    }

    candidate_rows: list[dict] = []
    summary: dict = {"models": {}, "city_models": {}, "rounding": {}}

    # full-population diagnostics
    diagnostics = [("BASELINE_4", "released", BASELINE_EDGES)]
    for k in (4, 5, 6):
        for method, func in method_funcs.items():
            diagnostics.append((f"K{k}R_{method}", method, func(all_values, k)))
    for model_id, method, edges in diagnostics:
        k = len(edges) + 1
        buckets = zone_members(rows, edges)
        bounds = [0.0, *edges, None]
        inst = boundary_instability(rows, edges, 0.05)
        for zi in range(k):
            row = _zone_row(model_id, method, k, "route_km", "FULL", zi + 1,
                            bounds[zi], bounds[zi + 1], buckets[zi], rows, city)
            row["boundary_instability_count"] = inst
            row["notes"] = "full-population route diagnostic; NOT a city tariff"
            candidate_rows.append(row)
        summary["models"][model_id] = {
            "k": k, "method": method, "edges": edges,
            "zone_counts": [len(b) for b in buckets],
            "min_share": _round(min(len(b) for b in buckets) / len(rows), 4),
            "max_share": _round(max(len(b) for b in buckets) / len(rows), 4),
        }

    # city deployable candidates
    city_specs = []
    for k in (4, 5, 6):
        for method, func in method_funcs.items():
            city_specs.append((f"CITY_K{k}R_{method}", method, func(city_values, k)))
        bc_edges, bc_method = thresholds_business_constrained(city_values, k)
        city_specs.append((f"CITY_K{k}R_business", bc_method, bc_edges))
    for model_id, method, edges in city_specs:
        k = len(edges) + 1
        buckets = zone_members(city, edges)
        bounds = [0.0, *edges, None]
        inst = boundary_instability(city, edges, 0.05)
        for zi in range(k):
            row = _zone_row(model_id, method, k, "route_km", "CITY", zi + 1,
                            bounds[zi], bounds[zi + 1], buckets[zi], rows, city)
            row["boundary_instability_count"] = inst
            row["notes"] = "city deployable candidate (outside_km=0)"
            candidate_rows.append(row)
        summary["city_models"][model_id] = {
            "k": k, "method": method, "edges": edges,
            "zone_counts": [len(b) for b in buckets],
            "min_share": _round(min(len(b) for b in buckets) / len(city), 4),
            "max_share": _round(max(len(b) for b in buckets) / len(city), 4),
            "rounding": rounding_variants(edges),
        }
    return candidate_rows, summary


def write_candidates(candidate_rows: list[dict]) -> None:
    with CANDIDATES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidate_rows)


def taxi_reference_a(in_city_km: float, outside_km: float) -> float:
    return max(TAXI_MIN_FARE, TAXI_CITY_RATE * in_city_km + TAXI_OUTSIDE_RATE * outside_km)


def taxi_reference_b(in_city_km: float, outside_km: float) -> float:
    return (TAXI_MIN_FARE + TAXI_CITY_RATE * max(0.0, in_city_km - 3.0)
            + TAXI_OUTSIDE_RATE * outside_km)


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
                ref_a = _round(taxi_reference_a(route_km, 0.0), 2)
                ref_b = _round(taxi_reference_b(route_km, 0.0), 2)
                fixed = _round(max(0.0, ref_a - TAXI_FIXED_COMMISSION), 2)
                percent = _round(TAXI_PERCENT_KEPT * ref_a, 2)
                best = _round(max(fixed, percent), 2)
                writer.writerow([
                    row["uid"], row["settlement"], row["district"], row["street"],
                    row["house"], _round(row["lat"], 6), _round(row["lon"], 6),
                    _round(route_km), "", "expected_km_osrm", _round(route_km), 0.0,
                    "CITY_ALL_IN", "", _round(route_km), ref_a, ref_b, fixed, percent,
                    best, row["zone_id"], "CITY_OWNER_ASSUMPTION",
                    "outside_city_km=0 by city doctrine; taxi = owner assumption",
                ])
            else:
                writer.writerow([
                    row["uid"], row["settlement"], row["district"], row["street"],
                    row["house"], _round(row["lat"], 6), _round(row["lon"], 6),
                    _round(route_km), "", "expected_km_osrm", "", "",
                    "OUTSIDE_SPLIT_UNKNOWN", "", "", "", "", "", "", "",
                    row["zone_id"], "EXTERNAL_SPLIT_UNKNOWN",
                    "external territory; in/out split unproven; bracket only",
                ])


def write_anchors() -> list[str]:
    text = BOUNDARY_CANDIDATES.read_text(encoding="utf-8")
    admin_ids = [line.split("id:")[1].strip() for line in text.splitlines() if "- id:" in line]
    anchors = [
        {"anchor_id": "PARKANY_KOTOVSKOGO_GAI_POST", "territory": "Парканы",
         "anchor_name": "Пост ГАИ на ул. Котовского (из Бендер в сторону Паркан)",
         "lat": "", "lon": "", "source_type": "OWNER_BRIEF_ONLY",
         "source_evidence": "owner-provided candidate boundary; NOT present in OSM/GIS data",
         "route_coverage_count": 0, "alternative_entry_exists": "UNKNOWN",
         "confidence": "UNPROVEN", "owner_confirmation_required": "True",
         "notes": "UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION — no coordinates invented"},
        {"anchor_id": "GISKA_EXTERNAL_ENTRY", "territory": "Гиска",
         "anchor_name": "Candidate Гиска entry corridor", "lat": "", "lon": "",
         "source_type": "NOT_ESTABLISHED",
         "source_evidence": "no proven single boundary anchor in data",
         "route_coverage_count": 0, "alternative_entry_exists": "UNKNOWN",
         "confidence": "UNPROVEN", "owner_confirmation_required": "True",
         "notes": "do not copy Parkany boundary; separate corridor evidence required"},
        {"anchor_id": "PROTYAGAILOVKA_EXTERNAL_ENTRY", "territory": "Протягайловка",
         "anchor_name": "Candidate Протягайловка entry corridor", "lat": "", "lon": "",
         "source_type": "NOT_ESTABLISHED",
         "source_evidence": "multiple corridor files exist but no proven single tariff boundary",
         "route_coverage_count": 0, "alternative_entry_exists": "UNKNOWN",
         "confidence": "UNPROVEN", "owner_confirmation_required": "True",
         "notes": "several corridors; boundary + outside length require evidence"},
        {"anchor_id": "SEVERNY_BOUNDARY", "territory": "Северный",
         "anchor_name": "Северный classification boundary", "lat": "", "lon": "",
         "source_type": "EVIDENCE_COLLECTION_ONLY",
         "source_evidence": "not auto-classified as Varnita, city or external",
         "route_coverage_count": 0, "alternative_entry_exists": "UNKNOWN",
         "confidence": "UNPROVEN", "owner_confirmation_required": "True",
         "notes": "OWNER_BOUNDARY_DECISION_REQUIRED"},
    ]
    header = ["anchor_id", "territory", "anchor_name", "lat", "lon", "source_type",
              "source_evidence", "route_coverage_count", "alternative_entry_exists",
              "confidence", "owner_confirmation_required", "notes"]
    with ANCHORS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(anchors)
    return admin_ids


def main() -> None:
    rows = load_addresses()
    assert len(rows) == 9216, f"expected 9216 addresses, got {len(rows)}"
    assert all(r["settlement"] != "Варница" for r in rows), "Varnita must not be present"

    city = [r for r in rows if r["is_city"]]
    reproduction = sum(1 for r in rows
                       if zone_for(r["route_km"], BASELINE_EDGES) == r["zone_id"])
    reproduction_strict = sum(1 for r in rows
                              if zone_for_released(r["route_km"], BASELINE_EDGES) == r["zone_id"])
    mismatches = baseline_mismatches(rows)
    write_mismatches(mismatches)

    candidate_rows, summary = build_all_models(rows)
    write_features(rows)
    write_candidates(candidate_rows)
    admin_ids = write_anchors()

    reg_by_uid = {r["uid"]: r for r in rows}
    controls = load_manual_controls(reg_by_uid)
    cm = summary["city_models"]
    model_defs = [
        ("BASELINE_4", BASELINE_EDGES, "FULL"),
        ("K5R_dp_optimal_jenks", summary["models"]["K5R_dp_optimal_jenks"]["edges"], "FULL"),
        ("CITY_K4R_dp_optimal_jenks", cm["CITY_K4R_dp_optimal_jenks"]["edges"], "CITY"),
        ("CITY_K5R_dp_optimal_jenks", cm["CITY_K5R_dp_optimal_jenks"]["edges"], "CITY"),
        ("CITY_K6R_dp_optimal_jenks", cm["CITY_K6R_dp_optimal_jenks"]["edges"], "CITY"),
    ]
    manual_rows = manual_validation_rows(controls, model_defs)
    write_manual_validation(manual_rows)

    kms = sorted(r["route_km"] for r in rows)
    summary["readiness"] = {
        "canonical_population": len(rows),
        "route_km_field": "expected_km",
        "baseline_zone_reproduction_le": reproduction,
        "baseline_zone_reproduction_strict": reproduction_strict,
        "baseline_mismatch_count": len(mismatches),
        "baseline_mismatch_ids": [m["address_id"] for m in mismatches],
        "baseline_mismatch_reasons": sorted({m["reason"] for m in mismatches}),
        "baseline_edges": BASELINE_EDGES, "baseline_max_km": BASELINE_MAX_KM,
        "registry_zone_counts": dict(sorted(Counter(r["zone_id"] for r in rows).items())),
        "territory_counts": dict(Counter(r["settlement"] for r in rows)),
        "city_addresses": len(city), "external_addresses": len(rows) - len(city),
        "route_km_min": _round(kms[0]), "route_km_median": _round(_percentile(kms, 0.5)),
        "route_km_p90": _round(_percentile(kms, 0.9)), "route_km_max": _round(kms[-1]),
        "manual_controls_total": len(controls),
        "manual_controls_city": sum(1 for c in controls if c["is_city"]),
        "admin_boundary_relation_ids": admin_ids,
    }
    summary["manual_validation"] = manual_summary(manual_rows)
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(summary["readiness"], ensure_ascii=False, indent=2))
    print("city models:", list(summary["city_models"]))


if __name__ == "__main__":
    main()
