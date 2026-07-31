# Yandex address-number reconciliation v1

The seven HIGH-confidence Yandex-only cards are preserved as a gross count. Each
is paired with the nearest canonical point on the same street, while evidence also
records any original conflict that exposed the card.

| Measure | Count |
|---|---:|
| Gross HIGH Yandex-only | 7 |
| Gross canonical-only within reconciliations | 5 |
| Paired zero-effect substitutions | 4 |
| Confirmed distinct Yandex additions | 2 |
| Unresolved pairs | 1 |
| Known provisional net inventory difference | 2 |

The numeric rule is `count(PLUS_ONE) - count(MINUS_ONE)`; `ZERO_SUBSTITUTION`,
`UNKNOWN`, and `UNRESOLVED` have no numeric effect.

Known provisional net effect: 2. One reconciliation remains unresolved and is excluded from the numeric net effect.

Visible-map rechecks on 2026-07-27 confirmed separate exact cards for Sovietskaya
31 and 36, and for Lenina 9 and 12. Industrialnaya 14А remains unresolved because
the canonical 12 query opened 12/3 instead.

## Immutable base + append-only recheck overlay

The base file
`data/interim/yandex-address-number-reconciliation-v1.csv` is an immutable record
of the original seven observations and is never edited in place. Every recheck is
appended to a separate layer,
`data/interim/yandex-address-number-reconciliation-recheck-v1.csv`, and the
analyzer derives the effective conclusion as *base overridden by the latest valid
recheck*. The known provisional net effect (+2) and the single remaining
unresolved pair are recomputed from this base + overlay; with the overlay removed
the effective result collapses back to the conservative base state (net 0, three
unresolved). See `address-number-reconciliation-recheck-v1.md` for the split
between original observation, recheck evidence, and effective conclusion.

This is not a final inventory difference for Bender or the surrounding
settlements. No release, canonical ID, coordinate, or territory assignment was
changed.
