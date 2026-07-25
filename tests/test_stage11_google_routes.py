"""Stage 11 — Google Routes oracle: request shape, disagreement rule, ToS guard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage11_google_routes import (  # noqa: E402
    FIELD_MASK,
    assert_no_google_polyline_in_public,
    build_payload,
    compute_routes,
    disagreement,
    parse_routes,
)

ORIGIN = (46.82388, 29.48313)
DEST = (46.83524, 29.46735)


# --- request shape -----------------------------------------------------------

def test_zone_requests_are_traffic_unaware_and_drive():
    p = build_payload(ORIGIN, DEST, "TRAFFIC_UNAWARE")
    assert p["travelMode"] == "DRIVE"
    assert p["routingPreference"] == "TRAFFIC_UNAWARE"


def test_live_order_requests_are_traffic_aware_optimal():
    p = build_payload(ORIGIN, DEST, "TRAFFIC_AWARE_OPTIMAL")
    assert p["routingPreference"] == "TRAFFIC_AWARE_OPTIMAL"


def test_shorter_distance_reference_route_is_requested():
    assert build_payload(ORIGIN, DEST, "TRAFFIC_UNAWARE")["requestedReferenceRoutes"] \
        == ["SHORTER_DISTANCE"]


def test_exact_latlng_is_sent_not_an_address_string():
    p = build_payload(ORIGIN, DEST, "TRAFFIC_UNAWARE")
    assert p["origin"]["location"]["latLng"]["latitude"] == ORIGIN[0]
    assert p["destination"]["location"]["latLng"]["longitude"] == DEST[1]


def test_field_mask_requests_every_required_field():
    for f in ("routes.distanceMeters", "routes.duration", "routes.staticDuration",
              "routes.polyline.encodedPolyline", "routes.routeLabels",
              "routes.warnings", "fallbackInfo"):
        assert f in FIELD_MASK


# --- no fabrication without a key -------------------------------------------

def test_without_an_api_key_nothing_is_invented(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    r = compute_routes(ORIGIN, DEST, "TRAFFIC_UNAWARE")
    assert r["status"] == "GOOGLE_API_KEY_MISSING"
    assert "routes" not in r          # no distance/duration conjured up
    assert r["payload"]["travelMode"] == "DRIVE"


# --- response parsing --------------------------------------------------------

def test_default_and_shorter_distance_routes_are_separated():
    body = {"routes": [
        {"distanceMeters": 6500, "duration": "410s", "staticDuration": "400s",
         "routeLabels": ["DEFAULT_ROUTE"], "polyline": {"encodedPolyline": "abc"}},
        {"distanceMeters": 4700, "duration": "430s", "staticDuration": "425s",
         "routeLabels": ["SHORTER_DISTANCE"], "polyline": {"encodedPolyline": "xyz"}},
    ]}
    p = parse_routes(body)
    assert p["default"]["distance_m"] == 6500
    assert p["shorter_distance"]["distance_m"] == 4700
    assert p["default"]["duration_s"] == 410.0
    assert p["shorter_distance"]["static_duration_s"] == 425.0


def test_warnings_and_fallback_info_are_kept():
    body = {"routes": [{"distanceMeters": 1, "routeLabels": ["DEFAULT_ROUTE"],
                        "warnings": ["closed road"]}],
            "fallbackInfo": {"routingMode": "FALLBACK_TRAFFIC_UNAWARE"}}
    p = parse_routes(body)
    assert p["warnings"] == ["closed road"]
    assert p["fallbackInfo"]["routingMode"] == "FALLBACK_TRAFFIC_UNAWARE"


# --- disagreement rule -------------------------------------------------------

def test_over_ten_percent_is_owner_review():
    pct, status = disagreement(4000.0, 4600.0)
    assert pct == 15.0 and status == "ROUTER_DISAGREEMENT_OWNER_REVIEW"


def test_within_ten_percent_is_agreement():
    _pct, status = disagreement(4000.0, 4200.0)
    assert status == "AGREEMENT_WITHIN_10PCT"


def test_missing_google_distance_stays_pending_not_agreement():
    pct, status = disagreement(None, 4200.0)
    assert pct is None and status == "PENDING_GOOGLE"


# --- Google Maps Platform terms guard ---------------------------------------

def test_no_google_polyline_leaks_into_docs_or_releases():
    assert assert_no_google_polyline_in_public() == []


def test_parsed_polyline_is_kept_under_a_private_key():
    body = {"routes": [{"distanceMeters": 1, "routeLabels": ["DEFAULT_ROUTE"],
                        "polyline": {"encodedPolyline": "secret"}}]}
    rec = parse_routes(body)["default"]
    # the polyline lives under a private "_"-prefixed key that public writers skip
    assert rec["_polyline"] == "secret"
    assert all(not k.startswith("_") or k == "_polyline" for k in rec)
