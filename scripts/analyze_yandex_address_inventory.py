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
RECOVERY = ROOT / "data/interim/recovered-nonresidential-address-candidates-v1.csv"
REVERSE = ROOT / "data/interim/yandex-reverse-street-audit-v1.csv"

VALID_STATUSES = {
    "EXACT_MATCH",
    "NORMALIZED_EQUIVALENT",
    "FACILITY_MATCH_WITH_ADDRESS",
    "FACILITY_MATCH_WITHOUT_HOUSE_NUMBER",
    "NEARBY_ADDRESS_ONLY",
    "DIFFERENT_STREET",
    "DIFFERENT_HOUSE_NUMBER",
    "SETTLEMENT_ONLY",
    "NOT_FOUND",
    "NON_DELIVERABLE_STRUCTURE",
    "DUPLICATE_EXISTING_ADDRESS",
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


def reverse_group_can_be_complete(row: dict[str, str]) -> bool:
    """Require evidence from all three longitudinal parts of a street."""
    fields = ("start_reviewed", "middle_reviewed", "end_reviewed")
    return all(row[field] == "True" for field in fields)


def main() -> None:
    classification = read_csv(CLASSIFICATION)
    sample = read_csv(SAMPLE)
    results = read_csv(RESULTS)
    recovery = read_csv(RECOVERY)
    reverse = read_csv(REVERSE)
    sample_by_id = {row["sample_id"]: row for row in sample}
    recovery_by_id = {row["candidate_id"]: row for row in recovery}
    if len(results) != len({row["sample_id"] for row in results}):
        raise ValueError("Duplicate forward-result sample IDs")
    canonical_results = []
    recovered_results = []
    for row in results:
        population_type = row["population_type"]
        if population_type == "CANONICAL_9216":
            if row["sample_id"] not in sample_by_id:
                raise ValueError(f"Canonical result outside sample: {row['sample_id']}")
            if row["address_id"] != sample_by_id[row["sample_id"]]["address_id"]:
                raise ValueError(f"Address mismatch for {row['sample_id']}")
            if row["source_candidate_id"]:
                raise ValueError(f"Canonical result has source candidate: {row['sample_id']}")
            row["sampling_weight"] = sample_by_id[row["sample_id"]]["sampling_weight"]
            canonical_results.append(row)
        elif population_type == "RECOVERED_EXCLUSION_CANDIDATE":
            if row["address_id"]:
                raise ValueError(f"Recovered result has canonical address ID: {row['sample_id']}")
            if row["source_candidate_id"] not in recovery_by_id:
                raise ValueError(f"Unknown recovered candidate: {row['source_candidate_id']}")
            recovered_results.append(row)
        else:
            raise ValueError(f"Invalid population type: {population_type}")
        if row["yandex_match_status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid result status: {row['yandex_match_status']}")

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
        "facility_match_with_address": counts["FACILITY_MATCH_WITH_ADDRESS"],
        "facility_match_without_house_number": counts[
            "FACILITY_MATCH_WITHOUT_HOUSE_NUMBER"
        ],
        "duplicate_existing_address": counts["DUPLICATE_EXISTING_ADDRESS"],
        "canonical_sample_size": len(sample),
        "canonical_processed": len(canonical_results),
        "recovered_candidate_total": len(recovery),
        "recovered_candidate_processed": len(recovered_results),
        "forward_processed_total": len(results),
        "reverse_street_groups_total": 316,
        "reverse_street_groups_reviewed": len(reverse),
        "high_confidence_yandex_only": sum(
            row["confidence"] == "HIGH" for row in read_csv(EXTRAS)
        ),
        "source_exclusions_total": len(recovery),
        "source_exclusions_recovered": sum(
            row["source_recovery_status"].startswith("RECOVERED_FROM_")
            for row in recovery
        ),
        "source_exclusions_blocked": sum(
            row["source_recovery_status"] == "BLOCKED_SOURCE_NOT_FOUND"
            for row in recovery
        ),
    }
    for key, value in expected.items():
        if checkpoint[key] != value:
            raise ValueError(f"Checkpoint {key}={checkpoint[key]!r}, expected {value!r}")
    if checkpoint["complete"]:
        raise ValueError("Partial checkpoint must not be complete")
    for row in reverse:
        claims_complete = row["review_status"] == "COMPLETE_FOR_VISIBLE_MAP"
        if claims_complete and not reverse_group_can_be_complete(row):
            raise ValueError(f"Incomplete longitudinal review: {row['street_audit_id']}")

    rate, lower, upper = weighted_rate(
        canonical_results, {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"}
    )
    classes = Counter(row["deliverable_address_status"] for row in classification)
    extras = read_csv(EXTRAS)
    print(f"population={len(classification)}")
    print(f"deliverable={classes['DELIVERABLE']}")
    print(f"non_deliverable={classes['NON_DELIVERABLE_STRUCTURE']}")
    print(f"unknown={classes['UNKNOWN_REQUIRES_REVIEW']}")
    print(f"sample={len(sample)}")
    print(f"canonical_processed={len(canonical_results)}")
    print(f"recovered_processed={len(recovered_results)}")
    print(f"forward_processed_total={len(results)}")
    print(f"weighted_match_rate={rate:.6f}")
    print(f"wilson_95={lower:.6f},{upper:.6f}")
    print(f"observed_extras={len(extras)}")
    print("conclusion=INCONCLUSIVE")


if __name__ == "__main__":
    main()
