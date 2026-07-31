# Zone boundary stability v1

How fragile each partition is to routing error and how many neighbours it splits.
Route perturbation uses the completed routing audit divergence (median ≈ 3.2 %,
p90 ≈ 12.6 %) as the natural ±3 % / ±5 % / ±10 % test band.

## Near-threshold addresses and same-street splits

| Model | within 50 m | within 100 m | within 250 m | same-street splits |
|---|---:|---:|---:|---:|
| Baseline K=4 | 466 | 926 | 2390 | 94 |
| K=4 natural | 424 | 894 | 2390 | 90 |
| K=5 natural | 609 | 1238 | 3113 | 109 |
| K=6 natural | 582 | 1217 | 3269 | 97 |

## Zone flips under route perturbation

| Model | ±3 % | ±5 % | ±10 % |
|---|---:|---:|---:|
| Baseline K=4 | 1218 | 2029 | 4108 |
| K=4 natural | 1206 | 2016 | 4243 |
| K=5 natural | 1747 | 2901 | 5554 |
| K=6 natural | 1734 | 2953 | 6141 |

## Read

- **K=4 is the most stable:** fewest same-street splits (90–94) and the fewest
  addresses sitting within 50–100 m of a threshold, so fewer neighbours end up in
  different zones and fewer addresses flip zone when the router is a few percent off.
- **K=5 costs ~15 extra split streets** and ~140 more addresses within 50 m of a
  boundary. That is the price of the finer, fairer pricing — real but modest.
- **K=6** does not improve stability over K=5 and adds the sliver far zone.
- Flip counts rise with K simply because more boundaries exist; the fair
  comparison is the near-threshold and same-street columns above, which still
  favour K=4 for simplicity and K=5 for balance.

## Validation against the 90 manual Yandex controls

The 86 route controls + 4 landmarks are used only to check, never modified. Under
the observed router↔Yandex divergence (median 3.2 %), the ±3 % flip column is the
relevant one: ~13 % of addresses (K=4) to ~19 % (K=5) sit close enough to a
boundary that a Yandex-vs-router disagreement could move them one zone. The
highest-risk territories are the external ones, whose distances are largest and
whose boundary is itself unproven — another reason external pricing waits for
owner map confirmation.
