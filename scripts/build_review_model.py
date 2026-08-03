"""Build the static /review/ route-geometry tariff model.

All 9,215 routed catalog rows use a committed OSRM route polyline.  A route is
external only after its first geometric intersection with the single transverse
owner-approved gate.  The canonical release, K4 polygons, Direct and prices remain
read-only inputs; only the review model's checkpoint is owner-approved.
"""

from __future__ import annotations

import csv
import json
import math
import unicodedata
from datetime import datetime
from pathlib import Path

from review_model_core import (
    base_price,
    decode_polyline6,
    external_surcharge,
    gvf,
    haversine_km,
    route_gate_metrics,
    weighted_jenks_breaks,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
POINTS = ROOT / "docs/data/final-address-zone-points.geojson"
RD = ROOT / "docs/review/data"
ROUTING = RD / "route-mindist-results.json"
ROUTE_GEOMETRIES = RD / "review-route-geometries.json"
PARKANY = RD / "parkany-route-boundary.json"
KISH_MANIFEST = RD / "kishinevskaya-authoritative-manifest.json"
GATE_CONFIG = ROOT / "config/review-gate.json"

ORIGIN = (29.48313, 46.82388)
SUPPORTED = {"Бендеры", "Парканы", "Гиска", "Протягайловка"}


def _norm(value: str | None) -> str:
    return unicodedata.normalize("NFKC", (value or "").strip().casefold())


def load_addresses() -> list[dict]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    features = json.loads(POINTS.read_text(encoding="utf-8"))["features"]
    coordinates: dict[str, tuple[float, float]] = {}
    properties: dict[str, dict] = {}
    for feature in features:
        uid = feature["properties"]["uid"]
        lon, lat = feature["geometry"]["coordinates"]
        coordinates[uid] = (lat, lon)
        properties[uid] = feature["properties"]
    rows = []
    for entry in registry:
        uid = entry["uid"]
        lat, lon = coordinates.get(uid, (None, None))
        point = properties.get(uid, {})
        canonical_km = point.get("central_km")
        old_zone = str(entry.get("zone_id", "")).strip()
        rows.append(
            {
                "uid": uid,
                "settlement": entry["settlement_ru"],
                "street": entry.get("street_ru") or "",
                "house": entry.get("housenumber") or "",
                "lat": lat,
                "lon": lon,
                "canonical_route_km": float(canonical_km) if canonical_km is not None else None,
                "old_k4_zone_id": int(old_zone) if old_zone.isdigit() else 0,
            }
        )
    return sorted(rows, key=lambda row: row["uid"])


def _transverse_gate(
    route: list[list[float]], index: int, half_length_m: float = 90
) -> list[list[float]]:
    center = route[index]
    before = route[max(0, index - 1)]
    after = route[min(len(route) - 1, index + 1)]
    latitude = math.radians(center[1])
    dx = (after[0] - before[0]) * 111_320 * math.cos(latitude)
    dy = (after[1] - before[1]) * 110_540
    length = math.hypot(dx, dy) or 1
    perpendicular_x = -dy / length
    perpendicular_y = dx / length
    return [
        [
            center[0]
            + side * half_length_m * perpendicular_x / (111_320 * math.cos(latitude)),
            center[1] + side * half_length_m * perpendicular_y / 110_540,
        ]
        for side in (-1, 1)
    ]


def _install_approved_gate(parkany: dict) -> dict:
    config = json.loads(GATE_CONFIG.read_text(encoding="utf-8"))
    checkpoint = config.get("checkpoint", {})
    if set(checkpoint) != {"lat", "lon", "status", "approved_at"}:
        raise ValueError("approved checkpoint must use the exact public checkpoint schema")
    if checkpoint["status"] != "owner_approved":
        raise ValueError("review gate must be owner_approved")
    datetime.fromisoformat(checkpoint["approved_at"].replace("Z", "+00:00"))
    index = config.get("route_index")
    route = parkany["route_lonlat"]
    if not isinstance(index, int) or not 1 <= index < len(route) - 1:
        raise ValueError("approved checkpoint route_index is invalid")
    center = route[index]
    if center != [checkpoint["lon"], checkpoint["lat"]]:
        raise ValueError("approved checkpoint coordinates must match its control-route index")
    gate = {
        "id": config["model_id"],
        "status": checkpoint["status"],
        "approved_at": checkpoint["approved_at"],
        "center_lonlat": center,
        "geometry": {"type": "LineString", "coordinates": _transverse_gate(route, index)},
        "corridor_route_index": index,
        "control_route_chainage_km": parkany["route_cum_km"][index],
        "provenance": {
            "method": (
                "owner-approved checkpoint with a transverse line perpendicular "
                "to the committed control route"
            ),
            "notes": (
                "Crossing is determined only from route geometry and this line; "
                "territory and fixed-distance inference are not used."
            ),
        },
    }
    parkany["note"] = "OWNER-APPROVED REVIEW CHECKPOINT — tariff formula remains unchanged"
    parkany.pop("provisional_gate", None)
    parkany.pop("provisional_boundary_km_from_origin", None)
    parkany["approved_gate"] = gate
    return gate


def _gate_geometry(parkany: dict) -> list[tuple[float, float]]:
    gate = parkany.get("approved_gate")
    if not gate or gate.get("status") != "owner_approved":
        raise ValueError("exactly one owner-approved gate is required")
    coordinates = gate.get("geometry", {}).get("coordinates", [])
    if gate.get("geometry", {}).get("type") != "LineString" or len(coordinates) != 2:
        raise ValueError("approved gate must be a two-point LineString")
    if "boundary_candidates" in parkany:
        raise ValueError("duplicate boundary_candidates must be provenance, not gate objects")
    return [tuple(coordinate) for coordinate in coordinates]


def _status(row: dict, seen: dict, route_km: float | None) -> tuple[str, float | str]:
    has_coordinate = isinstance(row["lat"], (int, float)) and isinstance(row["lon"], (int, float))
    key = (_norm(row["settlement"]), _norm(row["street"]), _norm(row["house"]))
    straight: float | str = ""
    if not has_coordinate or not row["street"] or not row["house"]:
        status = "invalid_address"
    elif row["settlement"] not in SUPPORTED:
        status = "outside_supported_area"
    elif key in seen:
        status = "duplicate"
    elif route_km is None:
        status = "unreachable"
    else:
        straight = round(haversine_km(ORIGIN, (row["lon"], row["lat"])), 3)
        status = "manual_review" if route_km > 12.0 else "routed"
    if status not in {"invalid_address", "outside_supported_area", "duplicate"}:
        seen.setdefault(key, row["uid"])
    return status, straight


def build_rows(addresses: list[dict], gate: list[tuple[float, float]]) -> list[dict]:
    distances = json.loads(ROUTING.read_text(encoding="utf-8"))["results"]
    geometry_payload = json.loads(ROUTE_GEOMETRIES.read_text(encoding="utf-8"))
    geometries = geometry_payload["routes"]
    if geometry_payload.get("route_count") != 9215 or len(geometries) != 9215:
        raise ValueError("route geometry inventory must contain exactly 9,215 routes")

    seen: dict[tuple[str, str, str], str] = {}
    output = []
    for row in addresses:
        uid = row["uid"]
        result = distances.get(uid)
        route_km = result[0] if result else None
        duration_km = result[1] if result else None
        status, straight = _status(row, seen, route_km)
        address = ", ".join(
            str(part) for part in (row["settlement"], row["street"], row["house"]) if part
        )
        record = {
            "uid": uid,
            "address": address,
            "territory": row["settlement"],
            "status": status,
            "canonical_route_km": row["canonical_route_km"],
            "route_km": route_km if route_km is not None else "",
            "route_km_duration_opt": duration_km if duration_km is not None else "",
            "straight_km": straight,
            "crosses_checkpoint": "",
            "intersection_chainage_km": "",
            "external_km": "",
            "base_price": "",
            "external_surcharge": "",
            "reference_price": "",
            "internal_zone": "",
            "routing_status": status,
            "old_k4_zone_id": row["old_k4_zone_id"],
            "lat": row["lat"],
            "lon": row["lon"],
        }
        if status == "routed":
            if uid not in geometries:
                raise ValueError(f"{uid}: routed address has no route geometry")
            geometry_km, encoded = geometries[uid]
            if abs(float(geometry_km) - route_km) > 0.002:
                raise ValueError(f"{uid}: geometry and published route distance disagree")
            metrics = route_gate_metrics(decode_polyline6(encoded), route_km, gate)
            external_km = float(metrics["external_km"])
            surcharge = external_surcharge(external_km)
            base = base_price(route_km)
            record.update(
                {
                    "crosses_checkpoint": bool(metrics["crosses_checkpoint"]),
                    "intersection_chainage_km": (
                        round(float(metrics["intersection_chainage_km"]), 4)
                        if metrics["intersection_chainage_km"] is not None
                        else ""
                    ),
                    "external_km": round(external_km, 4),
                    "base_price": round(base, 3),
                    "external_surcharge": round(surcharge, 3),
                    "reference_price": round(base + surcharge, 3),
                }
            )
        output.append(record)
    return output


def _zone_model(rows: list[dict]) -> tuple[int, list[float], dict[int, dict], dict[int, dict]]:
    prices = [row["reference_price"] for row in rows if row["status"] == "routed"]
    rounded_observations = [round(price, 1) for price in prices]
    evaluations = {}
    for class_count in range(3, 8):
        breaks = weighted_jenks_breaks(rounded_observations, class_count)
        evaluations[class_count] = {
            "breaks": [round(value, 3) for value in breaks],
            "gvf": round(gvf(prices, breaks), 4),
        }
    recommended = next(
        (class_count for class_count in range(3, 8) if evaluations[class_count]["gvf"] >= 0.90),
        4,
    )
    breaks = weighted_jenks_breaks(rounded_observations, recommended)

    def zone_of(price: float) -> int:
        index = 0
        while index < len(breaks) - 1 and price > breaks[index]:
            index += 1
        return index + 1

    stats: dict[int, dict] = {}
    for row in rows:
        if row["status"] != "routed":
            continue
        zone = zone_of(row["reference_price"])
        row["internal_zone"] = zone
        stat = stats.setdefault(
            zone,
            {
                "n": 0,
                "pmin": 1e9,
                "pmax": -1e9,
                "kmin": 1e9,
                "kmax": -1e9,
                "external": 0,
                "streets": {},
            },
        )
        stat["n"] += 1
        stat["pmin"] = min(stat["pmin"], row["reference_price"])
        stat["pmax"] = max(stat["pmax"], row["reference_price"])
        stat["kmin"] = min(stat["kmin"], row["route_km"])
        stat["kmax"] = max(stat["kmax"], row["route_km"])
        stat["external"] += int(row["external_surcharge"] > 0)
        street = row["address"].split(",")[1].strip()
        stat["streets"][street] = stat["streets"].get(street, 0) + 1
    for stat in stats.values():
        for key in ("pmin", "pmax", "kmin", "kmax"):
            stat[key] = round(stat[key], 3)
        stat["share_pct"] = round(100 * stat["n"] / len(prices), 1)
        stat["examples"] = [
            street
            for street, _count in sorted(stat["streets"].items(), key=lambda item: -item[1])[:4]
        ]
        del stat["streets"]
    return recommended, breaks, stats, evaluations


def _kishinevskaya(rows: list[dict]) -> tuple[list[dict], dict]:
    manifest = json.loads(KISH_MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    authoritative = {entry["uid"] for entry in entries if entry["included"]}
    if len(authoritative) != 34:
        raise ValueError("Kishinevskaya manifest must contain exactly 34 included UIDs")
    candidates = {row["uid"] for row in rows if "Кишинёв" in row["address"]}
    if candidates != {entry["uid"] for entry in entries}:
        raise ValueError("Kishinevskaya manifest does not cover every catalog candidate")
    details = []
    for row in rows:
        if row["uid"] not in authoritative:
            continue
        details.append(
            {
                "id": row["uid"],
                "address": row["address"],
                "old_km": row["canonical_route_km"],
                "new_km": row["route_km"],
                "duration_opt_km": row["route_km_duration_opt"],
                "status": row["status"],
                "reason": (
                    "shortest-distance route selected (was duration-optimal detour)"
                    if row["route_km"] != ""
                    and row["route_km_duration_opt"] != ""
                    and row["route_km"] < row["route_km_duration_opt"] - 0.05
                    else "no shorter alternative — distance unchanged"
                ),
            }
        )
    return details, manifest


def _write_csv(rows: list[dict]) -> None:
    columns = [
        "uid", "address", "territory", "status", "canonical_route_km", "route_km",
        "route_km_duration_opt", "straight_km", "crosses_checkpoint",
        "intersection_chainage_km", "external_km", "base_price", "external_surcharge",
        "reference_price", "internal_zone", "routing_status", "old_k4_zone_id",
    ]
    with (RD / "reference-tariff-v3.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_browser_data(rows: list[dict], recommended: int, breaks: list[float]) -> None:
    status_code = {"routed": 1, "duplicate": 2, "outside_supported_area": 4,
                   "unreachable": 5, "manual_review": 6}
    points = []
    index = []
    for row in rows:
        if not isinstance(row["lon"], (int, float)):
            continue
        zone = row["internal_zone"] if row["status"] == "routed" else 0
        price = row["reference_price"] if row["status"] == "routed" else None
        points.append([row["uid"], round(row["lon"], 5), round(row["lat"], 5), zone,
                       status_code.get(row["status"], 0), price, row["old_k4_zone_id"]])
        index.append([row["uid"], row["address"], round(row["lon"], 5),
                      round(row["lat"], 5), row["status"], row["route_km"],
                      row["old_k4_zone_id"], zone, price])
    (RD / "zone-points.json").write_text(
        json.dumps({"expected": len(rows), "plotted": len(points),
                    "recommended_zone_count": recommended,
                    "breaks": [round(value, 3) for value in breaks], "points": points},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8", newline="\n",
    )
    (RD / "address-index.json").write_text(
        json.dumps({"schema": ["uid", "address", "lon", "lat", "status", "route_km",
                                   "old_k4_zone_id", "internal_zone", "reference_price"],
                    "addresses": index}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8", newline="\n",
    )


def main() -> int:
    parkany = json.loads(PARKANY.read_text(encoding="utf-8"))
    approved_gate = _install_approved_gate(parkany)
    gate = _gate_geometry(parkany)
    rows = build_rows(load_addresses(), gate)
    recommended, breaks, zone_stats, evaluations = _zone_model(rows)
    kishinevskaya, manifest = _kishinevskaya(rows)
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    priced = sum(row["status"] == "routed" for row in rows)

    control_metrics = route_gate_metrics(
        [tuple(coordinate) for coordinate in parkany["route_lonlat"]],
        parkany["osrm_total_km"],
        gate,
    )
    summary = {
        "model": "review delivery-tariff model with owner-approved checkpoint",
        "origin": {"lat": ORIGIN[1], "lon": ORIGIN[0]},
        "distance_source": "committed OSRM shortest-distance route geometry per routed address",
        "formula": {"base": "14 if km<=3 else 14+(km-3)*4",
                    "external_surcharge": "max(5, external_km*2) after geometric gate crossing",
                    "rejected": "18 / 6 / 10"},
        "gate": approved_gate,
        "catalog_total": len(rows),
        "status_counts": status_counts,
        "status_sum": sum(status_counts.values()),
        "status_sum_equals_9216": sum(status_counts.values()) == 9216,
        "priced_addresses": priced,
        "jenks_algorithm": "frequency-weighted dynamic programming on rounded 0.1 price levels",
        "jenks_input_observation_count": priced,
        "jenks_distinct_level_count": len({round(row["reference_price"], 1)
                                             for row in rows if row["status"] == "routed"}),
        "zone_candidates_gvf": evaluations,
        "recommended_zone_count": recommended,
        "recommended_breaks_price": [round(value, 3) for value in breaks],
        "zone_stats": {str(zone): zone_stats[zone] for zone in sorted(zone_stats)},
        "routes_crossing_gate": sum(
            row["status"] == "routed" and row["crosses_checkpoint"] for row in rows
        ),
        "routes_not_crossing_gate": sum(
            row["status"] == "routed" and not row["crosses_checkpoint"] for row in rows
        ),
        "kishinevskaya": kishinevskaya,
        "kishinevskaya_total": len(kishinevskaya),
        "kishinevskaya_catalog_candidates_total": len(manifest["entries"]),
        "kishinevskaya_excluded": [entry for entry in manifest["entries"] if not entry["included"]],
        "kishinevskaya_fixed_count": sum(
            "shortest" in item["reason"] for item in kishinevskaya
        ),
        "parkany_control_km": parkany["osrm_total_km"],
        "parkany_control_gate_metrics": control_metrics,
        "status": "OWNER-APPROVED CHECKPOINT — tariff formula unchanged",
    }
    PARKANY.write_text(
        json.dumps(parkany, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    _write_csv(rows)
    _write_browser_data(rows, recommended, breaks)
    (RD / "reference-tariff-v3-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps({"catalog": len(rows), "priced": priced, "zones": recommended,
                      "breaks": summary["recommended_breaks_price"],
                      "crossing": summary["routes_crossing_gate"],
                      "kishinevskaya": len(kishinevskaya)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
