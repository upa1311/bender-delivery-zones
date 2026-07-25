# Stage 09C — Khomutyanovka brewery / Ленинский rail corridor

**Read-only. No OSM edit, no immutable release, no Direct, no price, no new zone.
owner_review_required.**

## The crossing exists and OSRM sees it — both directions

Owner ground truth: a car path centre → пивзавод (ул. Дружбы 7, 46.80229/29.47607)
→ **Ленинский rail crossing** → Хомутяновка. Reading OSM nodes near the brewery
(`docs/data/stage-09c-khomutyanovka-crossing.csv`):

- **5 car ways** cross the rail on a **shared `railway=level_crossing` node**,
  including a **primary two-way crossing** (OSM way **115331526**, `highway=primary`,
  `oneway=no`, level-crossing nodes **7996326105 / 1303507563** at ~46.8010,
  29.4784), plus service-road crossings and two primary **BRIDGE** spans (layer 2).
- Every one is **present in the local PBF and the OSRM graph, forward AND reverse**
  (`present_in_osrm_forward` and `present_in_osrm_reverse` = true).

So OSRM **does** see the brewery/Ленинский crossing in both directions. There is
no broken connectivity, no wrong access, no missing shared node here.

## Does the current fastest route overstate Khomutyanovka distance? NO

For 47 control Khomutyanovka homes (near / middle / far + 36 in Zone 3–4):
`docs/data/stage-09c-khomutyanovka-comparison.csv`.

| metric | result |
|---|---|
| homes with an OVERSTATED route (fastest > 10 % over the best valid) | **1 / 47** |
| median (fastest km − shortest km) for Zone 3–4 homes | **0.00** (fastest == shortest) |
| homes whose fastest route uses the brewery primary crossing | 0 (they use nearer optimal crossings) |
| forced route via the brewery crossing | **longer** than the current fastest for every sampled home |

So the current fastest route to Khomutyanovka is already the shortest — the
brewery corridor is a real car crossing but does **not** shorten these trips
(forcing it adds a southern detour). The one overstated home is flagged for review.

## Verdict

`ROUTE_CORRECT`. The Ленинский/brewery crossing is real and in the graph, but
Khomutyanovka's routes are not inflated by ignoring it. Any remaining Zone-3
question is the **cost-model / metric** decision (Stage 09), not routing. No zone
changed.
