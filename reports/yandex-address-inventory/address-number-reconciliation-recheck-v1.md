# Yandex address-number reconciliation — recheck overlay v1

This report documents the append-only recheck layer for the seven base
reconciliation observations. It exists to preserve immutable history: the base
file `data/interim/yandex-address-number-reconciliation-v1.csv` is never edited in
place, and every later visible-map recheck is appended to
`data/interim/yandex-address-number-reconciliation-recheck-v1.csv`.

A commit on this branch (`7493b2a`) had earlier rewritten three base rows
(YNR-0001, YNR-0002, YNR-0004) in place. That violated the append-only doctrine.
The base rows have been restored byte-for-byte to the parent commit
`75544b3d9c65ddc279ecd55b1f36d8e7b58f56d2`, and the recheck conclusions were moved
verbatim into the overlay layer below. No recheck evidence was lost, improved, or
re-decided; it was only relocated.

## How the effective conclusion is derived

For each reconciliation the analyzer takes the immutable base observation and, if
a recheck exists, overlays the **latest valid** recheck (deterministic order:
`checked_date`, then `recheck_id`). Exactly one effective row is produced per base
row. Reconciliations without a recheck keep their base observation unchanged.

## Original observation → recheck evidence → effective conclusion

### YNR-0001 / YOX-0001 — Советская 31 vs canonical Советская 36
- **Original protected observation:** `UNREVIEWED`, relationship `UNRESOLVED`,
  net `UNKNOWN`, confidence `LOW`.
- **Later recheck evidence (RCK-0001, 2026-07-27):** visible Yandex Maps searches
  opened separate exact cards for Советская 31 (46.823889, 29.482151) and
  canonical 36 (46.825005, 29.482420).
- **Effective analytical conclusion:** `NEIGHBORING_DISTINCT_BUILDINGS`,
  net `PLUS_ONE`, confidence `HIGH`.
- **Owner decision required:** yes — confirm the two cards are distinct deliverable
  buildings before any inventory count is treated as final.

### YNR-0002 / YOX-0002 — Ленина 9 vs canonical Ленина 12
- **Original protected observation:** `UNREVIEWED`, relationship `UNRESOLVED`,
  net `UNKNOWN`, confidence `LOW`.
- **Later recheck evidence (RCK-0002, 2026-07-27):** visible Yandex Maps searches
  opened separate exact cards for Ленина 9 (46.824900, 29.476994) and canonical 12
  (46.824142, 29.477542).
- **Effective analytical conclusion:** `NEIGHBORING_DISTINCT_BUILDINGS`,
  net `PLUS_ONE`, confidence `HIGH`.
- **Owner decision required:** yes — same confirmation as above.

### YNR-0004 / YOX-0004 — Индустриальная 14А vs canonical Индустриальная 12
- **Original protected observation:** `UNREVIEWED`, relationship `UNRESOLVED`,
  net `UNKNOWN`, confidence `LOW`.
- **Later recheck evidence (RCK-0004, 2026-07-27):** the 14А card was confirmed at
  (46.786349, 29.488601), but the canonical 12 query opened 12/3 at
  (46.788212, 29.488619), so the pair cannot yet be resolved.
- **Effective analytical conclusion:** still `UNRESOLVED`, net `UNKNOWN`,
  confidence `LOW`.
- **Owner decision required:** yes — needs a further manual map confirmation.

## Effective totals

| Measure | Value |
|---|---:|
| Base observations (immutable) | 7 |
| Recheck rows (append-only) | 3 |
| Effective rows | 7 |
| Effective PLUS_ONE | 2 |
| Effective ZERO_SUBSTITUTION | 4 |
| Effective UNKNOWN / UNRESOLVED | 1 |
| Known provisional net inventory difference | +2 |
| Unresolved reconciliations | 1 |

Known provisional net effect: 2. One reconciliation remains unresolved and is
excluded from the numeric net effect. This is not a full city inventory result and
no new release was issued.
