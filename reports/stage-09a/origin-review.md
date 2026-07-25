# Stage 09A — origin review

**Read-only. No override, no release, no Direct changes. owner_review_required.**

The three confirmed restaurant origins (`restaurant-origins.geojson`), snapped to
the OSRM car graph:

| origin | weight | lon, lat | snap distance | nearest road | on-road? |
|---|---|---|---|---|---|
| central | 0.85 | 29.48313, 46.82388 | **33.2 m** | real road | yes (< 40 m) |
| BAM | 0.10 | 29.47296, 46.84167 | 16.1 m | real road | yes |
| outer_other | 0.05 | 29.48801, 46.83396 | 7.1 m | real road | yes |

All three snap onto real car roads (< 40 m), none inside a courtyard/parking or on
the wrong side of a barrier — no `WRONG_ORIGIN` verdict.

## Notes for owner review

1. **Weights are 85 / 10 / 5**, not "85 / 15". The catalog `assignment_basis`
   string says `0.85_0.15`; the actual origins file is central 0.85 / BAM 0.10 /
   outer 0.05. Stage 09 reports both weightings (A = 85/15, B = 85/10/5); they
   barely move the edges, but the provenance string should be corrected at the
   next release.
2. **central snap = 33.2 m** is the largest of the three. It is still < 40 m and
   on a real road, but the owner may want to nudge the central origin coordinate a
   few metres onto the exact serving road for a cleaner snap.
3. Whether **85 / 10 / 5** matches the *actual* restaurant demand distribution is
   an owner data question; both weightings are provided so the owner can pick.

No origin coordinate was changed here.
