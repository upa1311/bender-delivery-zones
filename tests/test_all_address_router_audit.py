"""Integrity and resume tests for the full-address router evaluator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "data/interim/all-address-router-audit-v1.csv"

SPEC = importlib.util.spec_from_file_location(
    "evaluate_all_addresses_against_router",
    REPO / "scripts/evaluate_all_addresses_against_router.py",
)
assert SPEC and SPEC.loader
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)

PROTECTED_HASHES = {
    "config/bands.yml": "ebec96536b0f68ad8b2d41a9a04874dfd29acab56eec20f42a5e188ad00b6c8e",
    "docs/data/final-zone-polygons.geojson": (
        "cfc80697a7300890321319845704f1601f9a35317d80c99ec909d4be68e9db00"
    ),
    "docs/data/final-address-zone-catalog.csv": (
        "1a7207a5e5d6b868ba99662f86da99b08ab8dfb7cf215cab5b9f2e8f5dce4c87"
    ),
    "docs/data/tariff-band-metrics.json": (
        "5a15d0086d4f04428e0cc3d8065ae120841040e7c31e707876484b1bf9eefd70"
    ),
    "docs/catalog.js": "b641541c24143c3936052013e4ecf89d97886137ffe0abd506dabc38b11b380e",
    "docs/app.js": "75d768c54c06acce22221b2847ade2c5094b73a1fda0061dde6ec8d89940df4f",
}
RELEASES_HASH = "49edbc87a1f65b2a4c038bd395c5e9880038bf57208c98b9701564135704e9b4"
MANUAL_HASH = "58a71e47ac546f2788af0fc977709db169baea792bb866184e8ca926e177571c"
BASELINE_HASH = "fbbcc99658e66421dad18fc091c96fa4c9dbe6a1ac56c230610297526d7e0d95"


def rows(path: Path = AUDIT) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def releases_hash() -> str:
    digest = hashlib.sha256()
    root = REPO / "releases"
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def sample_address(address_id: str, lon: str) -> dict[str, str]:
    return {
        "address_id": address_id,
        "address_release_version": "test",
        "territory": "Test",
        "district": "Test",
        "street": "Test street",
        "house_number": "1",
        "destination_lat": "46.82",
        "destination_lon": lon,
    }


def sample_result(address: dict[str, str]) -> dict[str, str]:
    row = {field: "" for field in EVALUATOR.FIELDS}
    row.update(address)
    row.update(
        {
            "router_status": "ROUTABLE",
            "router_distance_km": "1.0000",
            "router_duration_min": "2.000",
            "straight_line_km": "0.9000",
            "detour_factor": "1.111",
            "snapped_origin_lat": "46.8241540",
            "snapped_origin_lon": "29.4833040",
            "origin_snap_distance_m": "33.23",
            "snapped_destination_lat": "46.8200000",
            "snapped_destination_lon": address["destination_lon"],
            "destination_snap_distance_m": "1.00",
            "route_node_count": "2",
            "route_first_nodes": "1;2",
            "route_last_nodes": "1;2",
            "terminal_node_signature": "terminal",
            "corridor_signature": "corridor",
            "bridge_or_rail": "NONE_OBSERVED",
            "uturn": "NO",
            "route_geometry_hash": "geometry",
            "probable_anomaly": "NONE",
            "anomaly_severity": "NONE",
            "owner_review_required": "False",
        }
    )
    return row


def test_canonical_input_hashes_and_actual_count():
    addresses, release = EVALUATOR.load_addresses()
    assert normalized_hash(EVALUATOR.REGISTRY) == EVALUATOR.REGISTRY_SHA256
    assert normalized_hash(EVALUATOR.COORDINATES) == EVALUATOR.COORDINATES_SHA256
    assert release["version"] == "1.1.0"
    assert len(addresses) == 9_216


def test_canonical_address_ids_are_unique():
    addresses, _ = EVALUATOR.load_addresses()
    assert len({row["address_id"] for row in addresses}) == len(addresses)


def test_audit_has_one_final_status_per_address():
    result = rows()
    assert len(result) == 9_216
    assert len({row["address_id"] for row in result}) == len(result)
    assert {row["router_status"] for row in result} <= EVALUATOR.VALID_STATUSES
    assert all(row["router_status"] for row in result)


def test_routable_rows_have_positive_distance_and_duration():
    for row in rows():
        if row["router_status"] == "ROUTABLE":
            assert float(row["router_distance_km"]) > 0
            assert float(row["router_duration_min"]) > 0


def test_unreachable_is_not_masked_as_router_error(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b'{"code":"NoRoute","routes":[]}'

    monkeypatch.setattr(EVALUATOR.urllib.request, "urlopen", lambda *a, **k: Response())
    status, _, error = EVALUATOR.request_route("http://local", (29.4, 46.8))
    assert status == "UNREACHABLE"
    assert error == "NoRoute"


def test_router_errors_remain_distinct_after_three_retries(monkeypatch):
    attempts = []

    def fail(*_args, **_kwargs):
        attempts.append(1)
        raise EVALUATOR.urllib.error.URLError("temporary")

    monkeypatch.setattr(EVALUATOR.urllib.request, "urlopen", fail)
    monkeypatch.setattr(EVALUATOR.time, "sleep", lambda *_: None)
    status, _, _ = EVALUATOR.request_route("http://local", (29.4, 46.8))
    assert status == "ROUTER_ERROR"
    assert len(attempts) == 3


def test_resume_does_not_duplicate_addresses(tmp_path, monkeypatch):
    addresses = [sample_address("a", "29.48"), sample_address("b", "29.49")]
    output = tmp_path / "audit.csv"
    partial = tmp_path / "partial.csv"
    checkpoint = tmp_path / "checkpoint.json"
    discrepancies = tmp_path / "discrepancies.csv"
    discrepancies.write_text(
        "control_id,destination_lat,destination_lon,flag\n", encoding="utf-8"
    )
    monkeypatch.setattr(EVALUATOR, "OUTPUT", output)
    monkeypatch.setattr(EVALUATOR, "PARTIAL", partial)
    monkeypatch.setattr(EVALUATOR, "CHECKPOINT", checkpoint)
    monkeypatch.setattr(EVALUATOR, "DISCREPANCIES", discrepancies)
    monkeypatch.setattr(EVALUATOR, "load_addresses", lambda: (addresses, {}))
    monkeypatch.setattr(EVALUATOR, "crossing_points", lambda: [])
    monkeypatch.setattr(
        EVALUATOR,
        "evaluate_address",
        lambda address, *_: sample_result(address),
    )
    EVALUATOR.write_csv(partial, [sample_result(addresses[0])])
    EVALUATOR.atomic_json(
        checkpoint,
        EVALUATOR.checkpoint_payload(
            [sample_result(addresses[0])], 2, "2026-01-01T00:00:00Z", "http://local", False
        ),
    )
    result = EVALUATOR.run(
        argparse.Namespace(base_url="http://local", workers=1, overwrite=False)
    )
    assert len(result) == len({row["address_id"] for row in result}) == 2
    assert not partial.exists()


def test_same_response_produces_deterministic_row(monkeypatch):
    payload = {
        "routes": [
            {
                "distance": 1000,
                "duration": 120,
                "geometry": {"coordinates": [[29.483, 46.824], [29.49, 46.82]]},
                "legs": [
                    {
                        "steps": [
                            {"name": "Test street", "maneuver": {"modifier": "right"}}
                        ],
                        "annotation": {"nodes": [1, 2]},
                    }
                ],
            }
        ],
        "waypoints": [
            {"location": [29.483, 46.824], "distance": 1, "name": "Origin"},
            {"location": [29.49, 46.82], "distance": 1, "name": "Test street"},
        ],
    }
    monkeypatch.setattr(
        EVALUATOR,
        "request_route",
        lambda *_: ("ROUTABLE", payload, ""),
    )
    address = sample_address("a", "29.49")
    assert EVALUATOR.evaluate_address(address, "http://local", []) == (
        EVALUATOR.evaluate_address(address, "http://local", [])
    )


def test_origin_is_fixed_for_every_request():
    assert EVALUATOR.ORIGIN == (29.48313, 46.82388)
    origins = {
        (row["snapped_origin_lat"], row["snapped_origin_lon"])
        for row in rows()
        if row["router_status"] == "ROUTABLE"
    }
    assert len(origins) == 1


def test_checkpoint_is_complete_and_matches_output():
    checkpoint = json.loads(EVALUATOR.CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["complete"] is True
    assert checkpoint["total_addresses"] == checkpoint["processed_addresses"] == 9_216
    assert checkpoint["input_sha256"] == EVALUATOR.REGISTRY_SHA256


def test_golden_measurements_and_router_baseline_are_unchanged():
    assert normalized_hash(REPO / "docs/data/manual-yandex-measurements.csv") == MANUAL_HASH
    assert normalized_hash(REPO / "data/interim/router-baseline-v1.csv") == BASELINE_HASH


def test_address_zone_direct_and_pricing_inputs_are_unchanged():
    for relative, expected in PROTECTED_HASHES.items():
        assert normalized_hash(REPO / relative) == expected, relative


def test_immutable_releases_are_unchanged():
    assert releases_hash() == RELEASES_HASH


def test_completed_audit_is_fail_closed_without_overwrite():
    with pytest.raises(FileExistsError, match="completed audit exists"):
        EVALUATOR.run(
            argparse.Namespace(
                base_url=EVALUATOR.DEFAULT_BASE_URL,
                workers=1,
                overwrite=False,
            )
        )
