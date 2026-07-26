# Probability sample methodology v1

The 400-address sample is drawn from all 9,216 canonical rows before looking at
Yandex outcomes, using fixed seed `20260727`. Stratification combines territory,
street-size bucket, deliverable/unknown status, territory-specific geographic
quadrant, and ordinary/lettered/fractional number type. Every territory is present.

Within each stratum, simple random selection without replacement is used.
`inclusion_probability = selected_in_stratum / population_in_stratum` and
`sampling_weight = 1 / inclusion_probability`. Address IDs are unique. Existing
observations are linked only after selection and therefore cannot affect inclusion.

The older 2,565-row sample remains a targeted diagnostic sample and must not be
described as a pure probability sample.
