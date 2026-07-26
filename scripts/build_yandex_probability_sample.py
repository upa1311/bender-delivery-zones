"""Build a reproducible probability sample from the full canonical population."""

from __future__ import annotations

import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "data/interim/canonical-deliverable-address-classification-v1.csv"
FORWARD = ROOT / "data/interim/yandex-forward-address-validation-v1.csv"
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
OUTPUT = ROOT / "data/interim/yandex-probability-sample-v1.csv"
SEED = 20260727
SAMPLE_SIZE = 400
FIELDS = [
    "probability_sample_id",
    "address_id",
    "territory",
    "district",
    "street",
    "house_number",
    "lat",
    "lon",
    "deliverable_status",
    "street_group_size",
    "number_type",
    "geographic_stratum",
    "inclusion_probability",
    "sampling_weight",
    "selection_seed",
    "already_reviewed",
    "linked_forward_sample_id",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number_type(value: str) -> str:
    if "/" in value or "-" in value:
        return "FRACTIONAL"
    if re.search(r"[A-Za-zА-Яа-я]", value):
        return "LETTERED"
    return "ORDINARY"


def street_size_bucket(size: int) -> str:
    if size <= 5:
        return "SHORT_1_5"
    if size <= 20:
        return "MEDIUM_6_20"
    return "LONG_21_PLUS"


def _allocation(stratum_sizes: dict[str, int]) -> dict[str, int]:
    """Allocate 400 fixed slots proportionally with one slot per nonempty stratum."""
    if len(stratum_sizes) > SAMPLE_SIZE:
        raise ValueError("More nonempty strata than sample slots")
    total = sum(stratum_sizes.values())
    allocation = {key: 1 for key in stratum_sizes}
    remaining = SAMPLE_SIZE - len(allocation)
    quotas = {key: remaining * size / total for key, size in stratum_sizes.items()}
    for key, quota in quotas.items():
        allocation[key] += min(math.floor(quota), stratum_sizes[key] - 1)
    left = SAMPLE_SIZE - sum(allocation.values())
    order = sorted(
        stratum_sizes,
        key=lambda key: (quotas[key] - math.floor(quotas[key]), stratum_sizes[key], key),
        reverse=True,
    )
    while left:
        progress = False
        for key in order:
            if allocation[key] < stratum_sizes[key]:
                allocation[key] += 1
                left -= 1
                progress = True
                if not left:
                    break
        if not progress:
            raise ValueError("Unable to allocate all probability-sample slots")
    return allocation


def build_probability_sample() -> list[dict[str, str]]:
    population = read_csv(CLASSIFICATION)
    if len(population) != 9216:
        raise ValueError(f"Expected 9216 canonical rows, found {len(population)}")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    districts = {row["uid"]: row.get("district_ru") or "" for row in registry}
    groups = Counter(
        (row["territory"], districts[row["address_id"]], row["street"])
        for row in population
    )
    territory_medians: dict[str, tuple[float, float]] = {}
    by_territory: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in population:
        by_territory[row["territory"]].append(row)
    for territory, rows in by_territory.items():
        lats = sorted(float(row["lat"]) for row in rows)
        lons = sorted(float(row["lon"]) for row in rows)
        territory_medians[territory] = (lats[len(lats) // 2], lons[len(lons) // 2])

    strata: dict[str, list[dict[str, str]]] = defaultdict(list)
    annotations: dict[str, tuple[int, str, str]] = {}
    for row in population:
        district = districts[row["address_id"]]
        size = groups[(row["territory"], district, row["street"])]
        kind = number_type(row["house_number"])
        median_lat, median_lon = territory_medians[row["territory"]]
        north_south = "N" if float(row["lat"]) >= median_lat else "S"
        east_west = "E" if float(row["lon"]) >= median_lon else "W"
        geographic = f"{row['territory']}:{north_south}{east_west}"
        key = "|".join(
            (
                row["territory"],
                street_size_bucket(size),
                row["deliverable_address_status"],
                geographic,
                kind,
            )
        )
        strata[key].append(row)
        annotations[row["address_id"]] = (size, kind, geographic)

    allocation = _allocation({key: len(rows) for key, rows in strata.items()})
    rng = random.Random(SEED)
    selected: list[tuple[str, dict[str, str]]] = []
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda row: row["address_id"])
        chosen = rng.sample(candidates, allocation[key])
        selected.extend((key, row) for row in sorted(chosen, key=lambda row: row["address_id"]))
    if len(selected) != SAMPLE_SIZE:
        raise ValueError(f"Expected {SAMPLE_SIZE} selected rows, found {len(selected)}")
    ordering_rng = random.Random(SEED + 1)
    ordering_rng.shuffle(selected)

    # Selection-time links are frozen to the protected pre-sample observations.
    # Later probability observations must not feed back into sample construction.
    forward_links = {
        row["address_id"]: row["sample_id"]
        for row in read_csv(FORWARD)[:153]
        if row["population_type"] == "CANONICAL_9216"
    }
    output: list[dict[str, str]] = []
    for index, (key, row) in enumerate(selected, start=1):
        stratum_size = len(strata[key])
        selected_in_stratum = allocation[key]
        probability = selected_in_stratum / stratum_size
        size, kind, geographic = annotations[row["address_id"]]
        linked = forward_links.get(row["address_id"], "")
        output.append(
            {
                "probability_sample_id": f"YPS-{index:04d}",
                "address_id": row["address_id"],
                "territory": row["territory"],
                "district": districts[row["address_id"]],
                "street": row["street"],
                "house_number": row["house_number"],
                "lat": row["lat"],
                "lon": row["lon"],
                "deliverable_status": row["deliverable_address_status"],
                "street_group_size": str(size),
                "number_type": kind,
                "geographic_stratum": geographic,
                "inclusion_probability": f"{probability:.12f}",
                "sampling_weight": f"{1 / probability:.12f}",
                "selection_seed": str(SEED),
                "already_reviewed": "True" if linked else "False",
                "linked_forward_sample_id": linked,
            }
        )
    return output


def main() -> None:
    rows = build_probability_sample()
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"probability_sample={len(rows)}")
    print(f"already_reviewed={sum(row['already_reviewed'] == 'True' for row in rows)}")
    print(f"seed={SEED}")


if __name__ == "__main__":
    main()
