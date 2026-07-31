# Customer / driver balance v1

City addresses only (owner assumptions). External territories carry a bracket, not
a price. Full grid: `data/interim/zone-economics-scenarios-v1.csv` (5,184 rows:
city rate × min fare × fixed comm × percent comm × client discount × driver gap).

## The current flat 25 руб (city, 4,866 addresses)

| Bucket | Addresses | Share |
|---|---:|---:|
| Client **overpays** (25 > equivalent taxi) | 3,191 | 65.6 % |
| **Adequate** (within a taxi-comparable band) | 1,544 | 31.7 % |
| Driver **underpaid** (25 ≪ best taxi take) | 131 | 2.7 % |

Reading: a flat 25 руб is **too expensive for ~two thirds of city addresses** —
these are the near trips (zones 1–2) where an equivalent taxi is 18–24 руб. 25 руб
is close to right only for the mid/far city zone (≈ zone 3), and is too low for a
small far-city tail. **25 руб is effectively a "zone-3 price" charged to everyone.**
This is why a zoned fee (13/14/22–25/27–31) is fairer than one flat number.

## Balanced per-zone city fees (from the model tables)

| Model | Zone fees (руб) |
|---|---|
| Baseline K=4 | 13 / 14 / 24 / 30 |
| K=4 natural | 13 / 14 / 25 / 31 |
| K=5 natural | 13 / 14 / 22 / 27 / 33 |

All are integer, monotone, and cheaper than the equivalent taxi (client saving
≈ 5 руб/zone) while keeping the driver gap within ±0.5 руб — i.e. the driver earns
about what the 65 % taxi platform would leave them, and the client still pays less
than a taxi.

## Sensitivity (feasibility envelope, owner baseline city 6 / min 18 / fixed 5 / 35 %)

Share of city addresses where the client saves AND the driver gap stays within the
allowed limit:

| Client discount \ Driver gap | 0 руб | 3 руб | 5 руб | 15 % |
|---|---:|---:|---:|---:|
| 3 руб | 100 % | 100 % | 100 % | 100 % |
| 5 руб | 100 % | 100 % | 100 % | 100 % |
| 10 % | 100 % | 100 % | 100 % | 100 % |
| 20 % | 65.6 % | 99.9 % | 100 % | 100 % |

Under the owner's own assumptions the economics is **very forgiving**: almost any
modest discount keeps both sides satisfied. Only an aggressive 20 % client
discount combined with a zero driver gap fails (only 66 % of addresses) — that is
the one policy corner where the driver would lose more than nothing.

## External territories — bracket only (NOT a price)

No proven city/outside split, so only an uncertainty range (median route km at 6
vs 10 руб./км):

| Territory | Addresses | Median km | Lower (6/км) | Upper (10/км) |
|---|---:|---:|---:|---:|
| Парканы | 3,446 | 5.21 | 31.3 | 52.1 |
| Гиска | 399 | 6.20 | 37.2 | 62.0 |
| Протягайловка | 505 | 6.29 | 37.7 | 62.9 |

These brackets are **not** tariffs and **not** a basis for thresholds. The owner
must confirm the external boundary (Kotovskogo GAI post and the Гиска /
Протягайловка corridors) before any external fee can be set.
