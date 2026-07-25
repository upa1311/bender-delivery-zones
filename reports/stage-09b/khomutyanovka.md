# Stage 09B — Хомутяновка

> **CORRECTED by Stage 10B.** The counts below used `alternatives=3` as the
> "shortest route", which is NOT a shortest path. Against a TRUE distance-optimal
> Dijkstra over the same car graph the real counts are: Борисовка **308/511**,
> Хомутяновка **94/999** (not 5), Протягайловка **191/513** (not 13), Парканы
> **45/90**, Гиска 0/90. In particular the "Хомутяновка is route-correct"
> conclusion does NOT hold. See `reports/stage-10b/corridor-routing-truth.md`.

**Read-only. No OSM edit, no release, no Direct, no price, no new zone. owner_review_required.**

- Entries cataloged: 88 (address-hull perimeter incl. internal streets + rail crossings).
- Segment validation of the fastest-time route: **26 / 223 OWNER_REVIEW_ROUTE**
  (service/access-restricted segment) — far fewer than Борисовка.
- Metric gap: only **4 / 999** homes have a shortest route >10% shorter than the
  fastest-time route. So Хомутяновка's routes are mostly **valid and stable**.

**Verdict:** Хомутяновка Zone 3 is largely a **real in-city road distance**
(~5.3 km median). Fix the ~26 service-segment routes + a few snap cases at owner
review; the rest is the Stage 09 cost-model question, not a routing bug. No zone
proposed.

> **Verified in Stage 09C.** Checked against the owner's brewery / route-№5 south corridor: the Ленинский crossing is real and in the OSRM graph (both directions), but Khomutyanovka's fastest routes are already optimal (1/47 overstated, median fastest==shortest; forcing the corridor is longer). The "route-correct" conclusion therefore stands. See `reports/stage-09c/khomutyanovka-brewery-corridor.md`.
