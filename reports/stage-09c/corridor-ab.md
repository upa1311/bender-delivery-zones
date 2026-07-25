# Stage 09C — Corridors A & B (Хомутяновка) + Протягайловка continuation

**Read-only. No OSM edit, no release, no Direct, no price, no new zone.
owner_review_required. EasyWay web bot-blocked (HTTP 403) — verified vs OSM/OSRM.**

Owner ground truth — two independent car corridors sharing a trunk:
- **A**: центр → пл. Героев → Пивзавод → Маслоэкстракционный → Ечина
- **B**: центр → Московская → Первомайская → Некрасова → Ечина
- **trunk**: Ечина → Роддом → больница → Главана → Старого
- **Протягайловка**: Старого → Мира → Протягайловка

## Connectivity — proven by routing (not shared nodes)

Two named streets sharing 0 nodes only means they meet via a cross-street; the
real test is whether OSRM routes the hop. `docs/data/stage-09c-corridor-ab-
connectivity.csv` — every consecutive hop is in the OSRM graph, short, both
directions:

| hop | forward | reverse | oneway-asymmetric |
|---|---|---|---|
| Московская→Первомайская | 0.59 km | 0.38 km | yes |
| Первомайская→Некрасова | 0.37 km | 1.15 km | yes |
| Некрасова→Ечина | 0.10 km | 0.10 km | no |
| Ечина→Главана | 0.50 km | 0.50 km | no |
| Главана→Старого | 0.64 km | 0.64 km | no |
| Старого→Мира | 2.09 km | 2.77 km | yes (ramp) |

Both corridors are traversable in OSRM in both directions; three hops are
oneway-asymmetric (recorded for the driver's forward/return difference).

## Do the corridors shorten Хомутяновка? NO

All 999 verified Хомутяновка homes (`stage-09c-khomutyanovka-comparison.csv`):
- **corridorA_best = 0, corridorB_best = 0** — forcing either corridor never
  produces a shorter route than the unrestricted fastest/shortest;
- **5 / 999** homes have an overstated current route (>10 % over best valid);
- 171 homes get a *provisional* proposed zone via the shortest valid km (owner
  review only — mostly the same duration-vs-distance effect, 1 strictly cheaper).

So Хомутяновка is route-correct; the corridors confirm connectivity, they do not
fix distance. Consistent with `khomutyanovka.md`.
