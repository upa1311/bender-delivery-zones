"""Yandex Distance Matrix — licence gate, batching, request shape, fail-closed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from yandex_distance_matrix import (  # noqa: E402
    MAX_ELEMENTS_PER_REQUEST,
    batches,
    build_request,
    call_matrix,
    license_state,
    verdict,
)

DESTS = [{"lat": 46.83 + i / 1000, "lon": 29.47 + i / 1000} for i in range(250)]


# --- licence gate: storing results requires an attested licence -------------

def test_no_key_and_no_licence_blocks_calls(monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_LICENSE_ALLOWS_STORAGE", raising=False)
    st = license_state()
    assert st["may_call_api"] is False
    assert any("YANDEX_API_KEY" in b for b in st["blockers"])


def test_key_without_storage_licence_still_blocks(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "x")
    monkeypatch.delenv("YANDEX_LICENSE_ALLOWS_STORAGE", raising=False)
    st = license_state()
    assert st["may_call_api"] is False       # storage licence is mandatory for zoning


def test_licence_without_contract_reference_blocks(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "x")
    monkeypatch.setenv("YANDEX_LICENSE_ALLOWS_STORAGE", "true")
    monkeypatch.delenv("YANDEX_LICENSE_REF", raising=False)
    assert license_state()["may_call_api"] is False


def test_key_plus_attested_licence_unblocks(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "x")
    monkeypatch.setenv("YANDEX_LICENSE_ALLOWS_STORAGE", "true")
    monkeypatch.setenv("YANDEX_LICENSE_REF", "contract-123")
    st = license_state()
    assert st["may_call_api"] is True and st["licence_ref"] == "contract-123"


def test_without_prerequisites_no_request_is_sent(monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_LICENSE_ALLOWS_STORAGE", raising=False)
    r = call_matrix(DESTS[:5])
    assert r["status"] == "PREREQUISITE_NOT_MET"
    assert "body" not in r                    # nothing fabricated


# --- batching: never more than 100 elements per synchronous request ---------

def test_batches_never_exceed_the_element_limit():
    chunks = list(batches(DESTS))
    assert all(len(c) <= MAX_ELEMENTS_PER_REQUEST for _i, c in chunks)


def test_batching_covers_every_destination_exactly_once():
    seen = [d for _i, c in batches(DESTS) for d in c]
    assert len(seen) == len(DESTS)


def test_full_run_needs_93_requests_for_9216_addresses():
    assert -(-9216 // MAX_ELEMENTS_PER_REQUEST) == 93


def test_oversized_batch_is_rejected():
    with pytest.raises(ValueError):
        build_request(DESTS[:101])


# --- request shape -----------------------------------------------------------

def test_request_uses_driving_lat_lon_and_avoids_tolls():
    req = build_request(DESTS[:3])
    p = req["params"]
    assert p["mode"] == "driving"
    assert p["avoid_tolls"] == "true"
    assert p["origins"] == "46.82388,29.48313"          # latitude,longitude
    assert p["destinations"].count("|") == 2


def test_traffic_is_neutral_for_stable_zoning():
    # no departure_time -> static/neutral traffic
    assert "departure_time" not in build_request(DESTS[:2])["params"]


# --- fail-closed verdicts ----------------------------------------------------

def test_yandex_error_never_falls_back_to_osrm():
    assert verdict(None, 4.2, "HTTP_403") == "YANDEX_ERROR_OWNER_REVIEW"


def test_unreachable_is_owner_review_not_zone_4():
    v = verdict(None, 4.2, "OK")
    assert v == "UNREACHABLE_OWNER_REVIEW"
    assert "ZONE" not in v.upper().replace("OWNER_REVIEW", "")


def test_divergence_over_10pct_is_owner_review():
    assert verdict(4.0, 4.6, "OK") == "ROUTER_DISAGREEMENT_OWNER_REVIEW"


def test_agreement_within_10pct():
    assert verdict(4.0, 4.2, "OK") == "AGREEMENT_WITHIN_10PCT"


def test_missing_prerequisite_stays_pending():
    assert verdict(None, 4.2, "PREREQUISITE_NOT_MET") == "PENDING_YANDEX_PREREQUISITE"
