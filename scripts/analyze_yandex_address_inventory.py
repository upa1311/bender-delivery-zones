"""Validate the partial Yandex checkpoint and provide conservative statistics."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "data/interim/canonical-deliverable-address-classification-v1.csv"
SAMPLE = ROOT / "data/interim/yandex-address-validation-sample-v1.csv"
RESULTS = ROOT / "data/interim/yandex-forward-address-validation-v1.csv"
EXTRAS = ROOT / "data/interim/yandex-observed-extra-addresses-v1.csv"
CHECKPOINT = ROOT / "data/interim/yandex-address-validation-checkpoint-v1.json"

VALID_STATUSES = {
    "EXACT_MATCH",
    "NORMALIZED_EQUIVALENT",
    "NEARBY_ADDRESS_ONLY",
    "DIFFERENT_STREET",
    "DIFFERENT_HOUSE_NUMBER",
    "SETTLEMENT_ONLY",
    "NOT_FOUND",
    "NON_DELIVERABLE_STRUCTURE",
    "AMBIGUOUS_REQUIRES_REVIEW",
}


def eligible_for_deliverable_estimate(status: str) -> bool:
    return status == "DELIVERABLE"


def can_publish_exact_yandex_total(has_licensed_full_source: bool) -> bool:
    return has_licensed_full_source


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def wilson_interval(
    successes: float, total: float, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Return a Wilson score interval for binomial-like effective counts."""
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("Wilson counts must satisfy 0 <= successes <= total and total > 0")
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def weighted_rate(rows: list[dict[str, str]], positive: set[str]) -> tuple[float, float, float]:
    """Return rate and an effective-sample-size Wilson interval."""
    if not rows:
        raise ValueError("At least one observed row is required")
    weights = [float(row["sampling_weight"]) for row in rows]
    weighted_successes = sum(
        weight
        for row, weight in zip(rows, weights, strict=True)
        if row["yandex_match_status"] in positive
    )
    rate = weighted_successes / sum(weights)
    effective_n = sum(weights) ** 2 / sum(weight * weight for weight in weights)
    lower, upper = wilson_interval(rate * effective_n, effective_n)
    return rate, lower, upper


def audit_can_be_complete(
    sample_size: int,
    processed: int,
    represented_streets: int,
    population_streets: int,
    reverse_audit_complete: bool,
) -> bool:
    return (
        sample_size >= 1000
        and processed == sample_size
        and represented_streets == population_streets
        and reverse_audit_complete
    )


def main() -> None:
    classification = read_csv(CLASSIFICATION)
    sample = read_csv(SAMPLE)
    results = read_csv(RESULTS)
    sample_by_id = {row["sample_id"]: row for row in sample}
    if len(results) != len({row["sample_id"] for row in results}):
        raise ValueError("Duplicate forward-result sample IDs")
    for row in results:
        if row["sample_id"] not in sample_by_id:
            raise ValueError(f"Result outside sample: {row['sample_id']}")
        if row["address_id"] != sample_by_id[row["sample_id"]]["address_id"]:
            raise ValueError(f"Address mismatch for {row['sample_id']}")
        if row["yandex_match_status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid result status: {row['yandex_match_status']}")
        row["sampling_weight"] = sample_by_id[row["sample_id"]]["sampling_weight"]

    counts = Counter(row["yandex_match_status"] for row in results)
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    expected = {
        "sample_size": len(sample),
        "processed": len(results),
        "exact_match": counts["EXACT_MATCH"],
        "normalized_equivalent": counts["NORMALIZED_EQUIVALENT"],
        "nearby_only": counts["NEARBY_ADDRESS_ONLY"],
        "different_street": counts["DIFFERENT_STREET"],
        "different_house": counts["DIFFERENT_HOUSE_NUMBER"],
        "settlement_only": counts["SETTLEMENT_ONLY"],
        "not_found": counts["NOT_FOUND"],
        "non_deliverable": counts["NON_DELIVERABLE_STRUCTURE"],
        "ambiguous": counts["AMBIGUOUS_REQUIRES_REVIEW"],
    }
    for key, value in expected.items():
        if checkpoint[key] != value:
            raise ValueError(f"Checkpoint {key}={checkpoint[key]!r}, expected {value!r}")
    if checkpoint["complete"]:
        raise ValueError("Partial checkpoint must not be complete")

    rate, lower, upper = weighted_rate(results, {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"})
    classes = Counter(row["deliverable_address_status"] for row in classification)
    extras = read_csv(EXTRAS)
    print(f"population={len(classification)}")
    print(f"deliverable={classes['DELIVERABLE']}")
    print(f"non_deliverable={classes['NON_DELIVERABLE_STRUCTURE']}")
    print(f"unknown={classes['UNKNOWN_REQUIRES_REVIEW']}")
    print(f"sample={len(sample)}")
    print(f"processed={len(results)}")
    print(f"weighted_match_rate={rate:.6f}")
    print(f"wilson_95={lower:.6f},{upper:.6f}")
    print(f"observed_extras={len(extras)}")
    print("conclusion=INCONCLUSIVE")


if __name__ == "__main__":
    main()
