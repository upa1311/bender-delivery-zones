# Stage 09C — Khomutyanovka (verified against the south corridor)

> **CORRECTED by Stage 10B.** The counts below used `alternatives=3` as the
> "shortest route", which is NOT a shortest path. Against a TRUE distance-optimal
> Dijkstra over the same car graph the real counts are: Борисовка **308/511**,
> Хомутяновка **94/999** (not 5), Протягайловка **191/513** (not 13), Парканы
> **45/90**, Гиска 0/90. In particular the "Хомутяновка is route-correct"
> conclusion does NOT hold. See `reports/stage-10b/corridor-routing-truth.md`.

**Read-only. No OSM edit, no release, no Direct, no price, no new zone.
owner_review_required.**

The Stage 09B statement **"Khomutyanovka Zone 3 mostly route-correct" is CONFIRMED**
after checking the owner's brewery/route-№5 south corridor:

- The brewery/Ленинский crossing is real and in the OSRM graph both ways.
- For 47 control homes (36 in Zone 3–4): **1/47** overstated, **median
  fastest == shortest**, and **forcing the brewery corridor is longer** for every
  home. So Khomutyanovka trips are already optimal; the south corridor does not
  shorten them.

Remaining action → owner review: (a) the single overstated home; (b) the ~15–25
snap/service-segment cases noted in Stage 09B; (c) the cost-model/metric choice
(Stage 09). None of these is a routing bug fixable by adding a road. No zone
changed; no release.
