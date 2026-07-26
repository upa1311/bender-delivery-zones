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
OWNER_REVIEW = ROOT / "data/interim/recovered-candidate-owner-review-v1.csv"
PROBABILITY_SAMPLE = ROOT / "data/interim/yandex-probability-sample-v1.csv"
PROBABILITY_LINKS = ROOT / "data/interim/yandex-probability-observations-v1.csv"
RECHECK = ROOT / "data/interim/yandex-canonical-conflict-recheck-v1.csv"
RECONCILIATION = ROOT / "data/interim/yandex-address-number-reconciliation-v1.csv"

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

STATUS_ORDER = (
    "EXACT_MATCH",
    "NORMALIZED_EQUIVALENT",
    "FACILITY_MATCH_WITH_ADDRESS",
    "FACILITY_MATCH_WITHOUT_HOUSE_NUMBER",
    "DIFFERENT_HOUSE_NUMBER",
    "DIFFERENT_STREET",
    "NEARBY_ADDRESS_ONLY",
    "SETTLEMENT_ONLY",
    "NOT_FOUND",
    "AMBIGUOUS_REQUIRES_REVIEW",
    "NON_DELIVERABLE_STRUCTURE",
    "DUPLICATE_EXISTING_ADDRESS",
)


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


def probability_review_design(
    sample: list[dict[str, str]], links: list[dict[str, str]]
) -> dict[str, int | float]:
    """Derive and validate the current two-phase probability-review design."""
    sample_ids = [row["probability_sample_id"] for row in sample]
    link_ids = [row["probability_sample_id"] for row in links]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Duplicate probability-sample IDs")
    if len(link_ids) != len(set(link_ids)):
        raise ValueError("Duplicate probability-observation links")
    sample_by_id = {row["probability_sample_id"]: row for row in sample}
    if unknown_links := set(link_ids) - set(sample_by_id):
        raise ValueError(f"Probability links outside sample: {sorted(unknown_links)}")

    preexisting = []
    eligible_new = []
    for row in sample:
        already_reviewed = row["already_reviewed"]
        linked_forward_id = row["linked_forward_sample_id"]
        if already_reviewed == "True" and linked_forward_id:
            preexisting.append(row)
        elif already_reviewed == "False" and not linked_forward_id:
            eligible_new.append(row)
        else:
            raise ValueError(
                "Probability sample has inconsistent selection-time review state: "
                f"{row['probability_sample_id']}"
            )

    eligible_new_ids = {row["probability_sample_id"] for row in eligible_new}
    if not set(link_ids) <= eligible_new_ids:
        raise ValueError("New probability links overlap selection-time observations")
    if not eligible_new:
        raise ValueError("No rows are eligible for the second review phase")
    if not links or len(links) > len(eligible_new):
        raise ValueError("Invalid second-phase probability-review size")

    return {
        "preexisting_linked": len(preexisting),
        "eligible_new": len(eligible_new),
        "new_random_batch_reviewed": len(links),
        "new_random_batch_inclusion_probability": len(links) / len(eligible_new),
    }


def two_phase_hajek_rate(
    rows: list[dict[str, str | float]], positive: set[str]
) -> float:
    """Return the two-phase Hájek ratio estimate for reviewed probability rows."""
    if not rows:
        raise ValueError("At least one reviewed probability row is required")
    weights = [float(row["final_analysis_weight"]) for row in rows]
    denominator = sum(weights)
    numerator = sum(
        weight
        for row, weight in zip(rows, weights, strict=True)
        if row["yandex_match_status"] in positive
    )
    return numerator / denominator


def provisional_net_inventory_difference(rows: list[dict[str, str]]) -> int:
    """Count known signed effects while excluding unknown or unresolved effects."""
    effect_values = {
        "PLUS_ONE": 1,
        "MINUS_ONE": -1,
        "ZERO_SUBSTITUTION": 0,
        "UNKNOWN": 0,
        "UNRESOLVED": 0,
    }
    total = 0
    for row in rows:
        effect = row["net_inventory_effect"]
        if effect not in effect_values:
            raise ValueError(f"Invalid net inventory effect: {effect}")
        total += effect_values[effect]
    return total


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
    """Require longitudinal, branch, and facility evidence for a complete group."""
    fields = (
        "start_reviewed",
        "middle_reviewed",
        "end_reviewed",
        "side_branches_reviewed",
        "facility_sites_reviewed",
    )
    return all(row[field] == "True" for field in fields)


def status_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter(row["yandex_match_status"] for row in rows)
    return {status: counts[status] for status in STATUS_ORDER}


def probability_reviewed_rows(
    sample: list[dict[str, str]],
    links: list[dict[str, str]],
    results: list[dict[str, str]],
) -> list[dict[str, str | float]]:
    """Join independently selected probability rows to old or new observations."""
    design = probability_review_design(sample, links)
    new_probability = float(design["new_random_batch_inclusion_probability"])
    result_by_id = {row["sample_id"]: row for row in results}
    link_by_probability_id = {row["probability_sample_id"]: row for row in links}
    if len(result_by_id) != len(results):
        raise ValueError("Duplicate forward-result sample IDs")
    if len({row["forward_sample_id"] for row in links}) != len(links):
        raise ValueError("Duplicate forward IDs in probability-observation links")
    reviewed: list[dict[str, str | float]] = []
    for row in sample:
        forward_id = row["linked_forward_sample_id"]
        review_phase = "PREEXISTING_LINKED"
        second_probability = 1.0
        if not forward_id:
            link = link_by_probability_id.get(row["probability_sample_id"])
            forward_id = link["forward_sample_id"] if link else ""
            review_phase = "NEW_RANDOM_BATCH"
            second_probability = new_probability
        if not forward_id:
            continue
        if forward_id not in result_by_id:
            raise ValueError(f"Unknown forward observation: {forward_id}")
        result = result_by_id[forward_id]
        if result["address_id"] != row["address_id"]:
            raise ValueError(f"Probability address mismatch: {row['probability_sample_id']}")
        if review_phase == "NEW_RANDOM_BATCH":
            link = link_by_probability_id[row["probability_sample_id"]]
            if link["address_id"] != row["address_id"]:
                raise ValueError(
                    f"Probability link address mismatch: {row['probability_sample_id']}"
                )
            if not math.isclose(
                float(link["sampling_weight"]),
                float(row["sampling_weight"]),
                rel_tol=1e-12,
            ):
                raise ValueError(
                    f"Probability link weight mismatch: {row['probability_sample_id']}"
                )
        first_probability = float(row["inclusion_probability"])
        first_weight = float(row["sampling_weight"])
        if not 0 < first_probability <= 1 or not math.isclose(
            first_weight, 1 / first_probability, rel_tol=1e-9
        ):
            raise ValueError(
                f"Invalid first-stage weight: {row['probability_sample_id']}"
            )
        reviewed.append(
            {
                **result,
                "probability_sample_id": row["probability_sample_id"],
                "sampling_weight": row["sampling_weight"],
                "first_stage_inclusion_probability": first_probability,
                "first_stage_weight": first_weight,
                "review_phase": review_phase,
                "second_phase_inclusion_probability": second_probability,
                "final_analysis_weight": first_weight / second_probability,
                "geographic_stratum": row["geographic_stratum"],
                "street_group_size": row["street_group_size"],
            }
        )
    return reviewed


def main() -> None:
    classification = read_csv(CLASSIFICATION)
    sample = read_csv(SAMPLE)
    results = read_csv(RESULTS)
    recovery = read_csv(RECOVERY)
    reverse = read_csv(REVERSE)
    owner_review = read_csv(OWNER_REVIEW)
    extras = read_csv(EXTRAS)
    probability_sample = read_csv(PROBABILITY_SAMPLE)
    probability_links = read_csv(PROBABILITY_LINKS)
    rechecks = read_csv(RECHECK)
    reconciliations = read_csv(RECONCILIATION)
    sample_by_id = {row["sample_id"]: row for row in sample}
    probability_forward_ids = {
        row["forward_sample_id"]: row for row in probability_links
    }
    recovery_by_id = {row["candidate_id"]: row for row in recovery}
    if len(results) != len({row["sample_id"] for row in results}):
        raise ValueError("Duplicate forward-result sample IDs")
    canonical_results = []
    recovered_results = []
    for row in results:
        population_type = row["population_type"]
        if population_type == "CANONICAL_9216":
            if row["sample_id"] in sample_by_id:
                sample_address_id = sample_by_id[row["sample_id"]]["address_id"]
            elif row["sample_id"] in probability_forward_ids:
                sample_address_id = probability_forward_ids[row["sample_id"]]["address_id"]
            else:
                raise ValueError(f"Canonical result outside samples: {row['sample_id']}")
            if row["address_id"] != sample_address_id:
                raise ValueError(f"Address mismatch for {row['sample_id']}")
            if row["source_candidate_id"]:
                raise ValueError(f"Canonical result has source candidate: {row['sample_id']}")
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
    probability_reviewed = probability_reviewed_rows(
        probability_sample, probability_links, results
    )
    canonical_counts = status_counts(canonical_results)
    recovered_counts = status_counts(recovered_results)
    combined_counts = status_counts(results)
    paired_substitutions = sum(
        row["net_inventory_effect"] == "ZERO_SUBSTITUTION"
        for row in reconciliations
    )
    unresolved_reconciliations = sum(
        row["relationship_type"] == "UNRESOLVED" for row in reconciliations
    )
    provisional_net = provisional_net_inventory_difference(reconciliations)
    probability_design = probability_review_design(
        probability_sample, probability_links
    )
    probability_positive = {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"}
    probability_successes = sum(
        row["yandex_match_status"] in probability_positive
        for row in probability_reviewed
    )
    probability_rate = probability_successes / len(probability_reviewed)
    probability_two_phase_rate = two_phase_hajek_rate(
        probability_reviewed, probability_positive
    )
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
        "reverse_street_groups_complete": sum(
            row["review_status"] == "COMPLETE_FOR_VISIBLE_MAP" for row in reverse
        ),
        "medium_extras_rechecked": 6,
        "high_confidence_yandex_only": sum(
            row["confidence"] == "HIGH" for row in extras
        ),
        "rejected_yandex_only": sum(
            row["confidence"].startswith("REJECTED_") for row in extras
        ),
        "deliverable_candidates_owner_reviewed": len(owner_review),
        "source_exclusions_total": len(recovery),
        "source_exclusions_recovered": sum(
            row["source_recovery_status"].startswith("RECOVERED_FROM_")
            for row in recovery
        ),
        "source_exclusions_blocked": sum(
            row["source_recovery_status"] == "BLOCKED_SOURCE_NOT_FOUND"
            for row in recovery
        ),
        "probability_sample_total": len(probability_sample),
        "probability_sample_reviewed": len(probability_reviewed),
        "probability_preexisting_linked": probability_design["preexisting_linked"],
        "probability_new_review_eligible": probability_design["eligible_new"],
        "probability_new_random_batch_reviewed": probability_design[
            "new_random_batch_reviewed"
        ],
        "probability_new_second_phase_inclusion_probability": probability_design[
            "new_random_batch_inclusion_probability"
        ],
        "probability_descriptive_unweighted_rate": probability_rate,
        "probability_two_phase_hajek_rate": probability_two_phase_rate,
        "probability_interval_status": (
            "UNAVAILABLE_PENDING_LARGER_OR_COMPLETE_PROBABILITY_REVIEW"
        ),
        "targeted_sample_reviewed": sum(
            row["sample_id"] in sample_by_id for row in canonical_results
        ),
        "canonical_status_counts": canonical_counts,
        "recovered_status_counts": recovered_counts,
        "combined_status_counts": combined_counts,
        "gross_yandex_only_high": sum(
            row["confidence"] == "HIGH" for row in extras
        ),
        "gross_canonical_only": sum(
            row["gross_canonical_only"] == "True" for row in reconciliations
        ),
        "paired_number_substitutions": paired_substitutions,
        "provisional_net_inventory_difference": provisional_net,
        "unresolved_reconciliations": unresolved_reconciliations,
        "canonical_conflicts_rechecked": len(rechecks),
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

    targeted_weighted = []
    for row in canonical_results:
        if row["sample_id"] in sample_by_id:
            targeted_weighted.append(
                {**row, "sampling_weight": sample_by_id[row["sample_id"]]["sampling_weight"]}
            )
    rate, lower, upper = weighted_rate(
        targeted_weighted, {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"}
    )
    classes = Counter(row["deliverable_address_status"] for row in classification)
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
    print(f"reverse_groups_reviewed={len(reverse)}")
    print(
        "reverse_groups_complete="
        f"{sum(row['review_status'] == 'COMPLETE_FOR_VISIBLE_MAP' for row in reverse)}"
    )
    print(f"owner_candidates_reviewed={len(owner_review)}")
    print(f"probability_sample_total={len(probability_sample)}")
    print(f"probability_sample_reviewed={len(probability_reviewed)}")
    print(
        "probability_preexisting_linked="
        f"{probability_design['preexisting_linked']}"
    )
    print(f"probability_new_review_eligible={probability_design['eligible_new']}")
    print(
        "probability_new_random_batch_reviewed="
        f"{probability_design['new_random_batch_reviewed']}"
    )
    print(
        "probability_new_second_phase_inclusion_probability="
        f"{probability_design['new_random_batch_inclusion_probability']:.12f}"
    )
    print(f"probability_descriptive_unweighted_rate={probability_rate:.6f}")
    print(f"probability_two_phase_hajek_rate={probability_two_phase_rate:.6f}")
    print(
        "probability_interval="
        "UNAVAILABLE_PENDING_LARGER_OR_COMPLETE_PROBABILITY_REVIEW"
    )
    print(f"canonical_conflicts_rechecked={len(rechecks)}")
    print(f"paired_number_substitutions={paired_substitutions}")
    print(f"unresolved_reconciliations={unresolved_reconciliations}")
    print(f"provisional_net_inventory_difference={provisional_net}")
    print("conclusion=INCONCLUSIVE")


if __name__ == "__main__":
    main()
