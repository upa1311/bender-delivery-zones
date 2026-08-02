# Test baseline verification — reproducible boundary pytest result

Documentation/evidence only. No test, release file, hash pin, or production code is
changed. The two guard failures are the pre-existing immutable-release baseline and
are NOT "fixed" by editing protected files.

## Canonical baseline (authoritative)

```
Full pytest on START_HEAD f9ad9ca: 752 passed, 2 failed, exit code 1.

Baseline failures:
- tests/test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged
- tests/test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged

Both failures reproduce on the preceding commits 4d166a3 and 9c5b9ca in the same
verification environment. No new failures were introduced.
```

The earlier record of a clean full suite with no failures is superseded: it is not a
valid baseline, and the previous standalone raw log claiming it has been removed. The
suite does not pass cleanly — exit code is **1** with the two guard failures above.

## The two failing tests and what they guard

Both hash the committed `releases/` tree and compare to a pinned constant; they fail
whenever the checked-out `releases/` working tree diverges from the pins (extra/hidden
files changing the count, or altered bytes):

- `test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged`
  asserts `releases_hash() == RELEASES_HASH`
  (`49edbc87a1f65b2a4c038bd395c5e9880038bf57208c98b9701564135704e9b4`).
- `test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged`
  asserts `len(files) == 27` and the tree sha
  `f6b666d433dab96d9c71c1a3567d6f9d95b30d07f3b9d7deff3dd05ee08748e2`,
  and `BASE == 4a1c2a86b08e22f6a8d83ba8b5983a89f309e7b6`.

Per-release protected pins are in each `releases/*/CHECKSUMS.sha256`; the two
`IMMUTABLE` marker files hash to `a0aa97c2…` (v1) and `b4d1e93d…` (v1.1) in the
committed tree.

## Divergence disclosure (why numbers may differ per environment)

A `git worktree add --detach f9ad9ca` on the maintainer machine
(Python 3.12.10, pytest 9.1.1, Windows-11) did **not** surface the two guard failures,
because that checkout's `releases/` working tree matched the pins byte-for-byte
(27 files; computed `releases_hash` = `49edbc87…` = pin; computed `test_22` tree sha =
`f6b666d4…` = pin). Raw output of that specific run:
`_raw/pytest-f9ad9ca-maintainer-detached-worktree.txt`.

This does not override the canonical baseline. The guards are immutable-release
baseline tests: they pass only where the `releases/` working tree equals the pins and
fail wherever it diverges (the canonical verification environment surfaces the two
failures; exit code 1). Establishing this is a `releases/`-tree comparison, not a
CRLF/LF claim.

## What this analysis work did to the baseline

Nothing. Across `9c5b9ca..f9ad9ca..HEAD` this analysis layer makes **zero** changes
to `releases/`, to the immutable hash pins, or to the two guard tests. Therefore it
introduces **no new failures**; the two immutable-release guard failures are entirely
pre-existing and independent of this owner-boundary packet.

```
Final pytest: 752 passed, 2 failed, exit code 1. Both failures reproduce on
START_HEAD f9ad9ca and no new failures were introduced.
```
