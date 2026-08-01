# Balanced-zone fragmentation — minimum tariff steps v1

Candidate analysis, city-only, fixed-origin km, owner assumptions. Not applied to
production, Direct, releases or GitHub Pages.

## Question

How many contiguous flat-fee tariff steps are needed so that **every** zone is
100 %-coverage feasible under each policy? A contiguous set of city addresses is
policy-feasible iff its driver floor ≤ its client ceiling — then a single flat fee
satisfies every address in it. Extending a zone to a farther address only raises
the driver floor and never raises the client ceiling, so feasibility is monotone
under extension; greedy maximal extension therefore yields the **minimum** number
of zones (standard optimal-segmentation argument).

## Proven result

| Policy | Minimum zones for 100 % coverage |
|---|---:|
| DRIVER_CONSERVATIVE | 5 |
| **BALANCED** | **14** |
| CUSTOMER_FIRST | 9 |

**A flat-fee-per-zone BALANCED tariff needs ~14 steps** over the 4,866 city
addresses. Full minimal partition (each zone with its feasible fee):
`data/interim/zone-balanced-fragmentation-v1.csv`.

## Why so many

The near band (≤ 3.24 km) holds one big zone of 2,528 addresses because their taxi
reference is pinned at the 18 руб floor (zero spread → one flat fee works). Beyond
the floor, taxi reference grows at 6 руб/км, and BALANCED allows only a ~3 руб
(or 10 %) driver-gap window, so each far zone can span only ~0.5 км before a single
flat fee can no longer keep the driver within 3 руб AND the client saving ≥ 5 руб.
That splits the 3.2–7.5 км range into 13 thin far bands — 14 in total.

## Consequence

Fourteen flat tariff steps are impractical to operate and explain. This is the
quantitative case for **not** forcing a flat fee on the middle/far city zones and
instead using a simple **base + distance** formula there — developed separately as
a candidate (see `city-far-zone-base-distance-v1.md`), not applied to production.

Verdict: ANALYSIS_COMPLETE / OWNER_DECISION_REQUIRED.
