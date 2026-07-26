# Router repair v1 — before/after

No graph mutation passed the evidence threshold. The “after” run therefore
repeats the evaluator against the same local OSRM build to prove that the audit
itself introduces no routing regression.

## Aggregate comparison

| metric | baseline | after | change |
|---|---:|---:|---:|
| controls | 86 | 86 | 0 |
| routable | 86 | 86 | 0 |
| unreachable | 0 | 0 | 0 |
| median divergence | 3.2% | 3.2% | 0.0 pp |
| mean divergence | 5.9% | 5.9% | 0.0 pp |
| p90 divergence | 12.6% | 12.6% | 0.0 pp |
| divergence >5% | 25 | 25 | 0 |
| divergence >10% | 10 | 10 | 0 |
| divergence >20% | 7 | 7 | 0 |
| suspicious destination snap | 1 | 1 | 0 |

The baseline and after CSV files have the same SHA-256 and are byte-identical.

## Required large controls

| control | baseline divergence | after divergence | disposition |
|---|---:|---:|---|
| MY-002 | 36.0% | 36.0% | ADDRESS_REVIEW_REQUIRED |
| MY-X01 | 22.7% | 22.7% | NO_GRAPH_DEFECT_FOUND; extra landmark |
| MY-X02 | 20.6% | 20.6% | ADDRESS_REVIEW_REQUIRED; extra landmark |
| MY-018 | 28.9% | 28.9% | ADDRESS_REVIEW_REQUIRED |
| MY-005 | 15.3% | 15.3% | NO_GRAPH_DEFECT_FOUND |
| MY-019 | 25.0% | 25.0% | ADDRESS_REVIEW_REQUIRED |
| MY-020 | 24.8% | 24.8% | ADDRESS_REVIEW_REQUIRED |
| MY-054 | 14.7% | 14.7% | NO_GRAPH_DEFECT_FOUND |
| MY-063 | 28.7% | 28.7% | NO_GRAPH_DEFECT_FOUND |
| MY-065 | 10.4% | 10.4% | NO_GRAPH_DEFECT_FOUND |
| MY-073 | 25.6% | 25.6% | NO_GRAPH_DEFECT_FOUND |
| MY-075 | 23.2% | 23.2% | ADDRESS_REVIEW_REQUIRED |

MY-X01 and MY-X02 are outside the 86-control aggregate, as required by their
extra-landmark status.

## Regression audit

- divergence increase greater than 3 percentage points: **0**;
- new route above 10%: **0**;
- new unreachable: **0**;
- increased snap distance: **0**;
- lost previously available corridor: **0**;
- baseline routes at or below 5% that regressed: **0**.

## Acceptance result

The diagnostic-only result meets the safety criteria: no route was lost, no
fictional connection or per-control override was introduced, the number above
10% did not increase, and median divergence did not worsen. Large differences
are retained honestly as address/vendor/route-choice cases instead of being
forced toward artificial zero.

No zone, boundary, threshold, address base, Direct integration, price, tariff,
routing graph, or immutable release changed.
