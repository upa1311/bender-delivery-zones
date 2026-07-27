# Probability sample methodology v1

The 400-address sample is drawn from all 9,216 canonical rows before looking at
Yandex outcomes, using fixed seed `20260727`. Stratification combines territory,
street-size bucket, deliverable/unknown status, territory-specific geographic
quadrant, and ordinary/lettered/fractional number type. Every territory is present.

Within each stratum, simple random selection without replacement is used.
`inclusion_probability = selected_in_stratum / population_in_stratum` and
`sampling_weight = 1 / inclusion_probability`. Address IDs are unique. Existing
observations are linked only after selection and therefore cannot affect inclusion.

## Second-phase review model

The current review checkpoint is explicitly two-phase. The sample file derives 33
`PREEXISTING_LINKED` rows from its frozen selection-time links; their second-phase
inclusion probability is 1. The remaining 367 rows form the eligible pool for the
outcome-independent random review order. The link file now contains 267 reviewed
rows from that pool, so every `NEW_RANDOM_BATCH` row has second-phase inclusion
probability `267 / 367`.

The second-phase selection rule is
`FIRST_N_ELIGIBLE_IN_FROZEN_SAMPLE_ORDER`: for batch size N, link rows must equal
the first N rows in the physical probability-sample CSV order for which
`already_reviewed == False` and `linked_forward_sample_id == ""`. Equality is
position-by-position in link CSV order, not merely set membership. The analyzer
rejects replacements, reordered links, and arbitrary eligible subsets.

For every reviewed row, the analyzer derives and validates
`first_stage_inclusion_probability`, `first_stage_weight`, `review_phase`,
`second_phase_inclusion_probability`, and `final_analysis_weight`. The final weight
is `first_stage_weight / second_phase_inclusion_probability`. The counts 33, 367,
and 267 are derived from the sample and link files and checked for unique IDs,
non-overlap, frozen selection order, and valid observation links.

The interim exact+normalized point estimate is the Hájek ratio
`sum(final_analysis_weight * outcome) / sum(final_analysis_weight)`. A defensible
stratified two-phase variance estimate cannot be reconstructed from the current
partial review alone, so no design-based confidence interval is published pending
a larger or completed probability review.

The older 2,565-row sample remains a targeted diagnostic sample and must not be
described as a pure probability sample.
