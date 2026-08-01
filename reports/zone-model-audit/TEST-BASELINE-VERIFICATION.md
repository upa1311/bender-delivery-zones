# Test baseline verification — correction note

This note records the honest pytest baseline and corrects earlier inaccuracies. It
changes no code and fixes no baseline failure by editing protected release files.

## Corrections to the previous version of this note

The previous version of this note was wrong on two points, now corrected:

1. It named the wrong failing tests. It listed
   `test_release.py::test_release_checksums_match` and
   `test_release_v11.py::test_checksums_match_and_manifest_agrees`. Those were
   observed only in an `autocrlf=true` (CRLF) experiment; they are **not** the
   canonical immutable-release guard tests. The correct immutable-release guard
   tests are:
   - `tests/test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged`
   - `tests/test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged`
2. It implied a clean run proves "0 failed everywhere" and gave a CRLF-based
   explanation. That over-claimed. This version reports the raw measured result and
   the exact guard mechanism instead.

The earlier phrasings **"752 passed, 0 failed"** / **"753 passed, 0 failed"** must NOT
be read as "all tests pass" — see the divergence section below.

## Independent reviewer baseline (mandated formulation)

> **Full pytest on START_HEAD 4d166a3: 751 passed, 2 failed, exit code 1.**
>
> Baseline failures:
> - tests/test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged
> - tests/test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged
>
> Both failures reproduce on the previous comparison commit 9c5b9ca (750 passed, 2
> failed); no new failures were introduced.

These are pre-existing immutable-release guard tests. This analysis layer never
touches `releases/` (0 `releases/` changes across 6d4679c..HEAD), so it introduces
zero new failures under any baseline.

## What this environment actually measured (raw, reproducible)

Fresh clean-LF clone of START_HEAD `4d166a3` (`git -c core.autocrlf=false clone …`),
full pytest: **753 passed, 0 failed, exit code 0**.

After this correction commit (adds one passing regression test, `test_132`), the full
pytest in this environment is **754 passed, 0 failed, exit code 0**. Raw output:
`reports/zone-model-audit/_raw/pytest-autocrlf-false.txt`. In this clean checkout the
two guard tests **pass**, because the committed `releases/` tree matches the pinned
hash exactly:

- `test_immutable_releases_are_unchanged` asserts `releases_hash() == RELEASES_HASH`.
  Computed here: `49edbc87a1f65b2a4c038bd395c5e9880038bf57208c98b9701564135704e9b4`
  == the pin. Pass.
- `test_22_immutable_releases_are_unchanged` asserts `len(files) == 27` and a pinned
  sha over the LF-normalised `releases/` tree. Here `len(files) == 27` and the sha
  matches. Pass.

Both guard hashes normalise CRLF→LF before hashing, so they are line-ending
independent; a CRLF checkout does not flip them (verified). A separate set of
release/vendored-checksum tests IS CRLF-fragile and fails on an `autocrlf=true`
checkout (7 failures: `test_release.py` ×3, `test_release_v11.py`, `test_bands.py`
×2, `test_lipcani_classification.py`) — those are a different, also pre-existing
baseline.

## Divergence and honest conclusion

The reviewer's environment reports the two guard tests failing (751 passed, 2 failed);
this environment reproduces 753 passed, 0 failed on a clean LF clone and never sees
those two fail (LF or CRLF). The guard tests fail **iff** the `releases/` tree differs
from the pinned hash (≠27 files or altered content). In this commit the `releases/`
tree is byte-for-byte the committed baseline (27 files, hash == pin), so they pass
here. Any environment that sees them fail has a `releases/` tree difference that is
**not** produced by this work.

- The exact `passed`/`failed` split therefore depends on the runner's `releases/`
  tree and (for the separate release-checksum tests) its line-ending conversion.
- `passed` and `failed` are never summed into a single "passed" figure.
- No claim of "all tests pass" is made: the immutable-release / release-checksum
  guards are the pre-existing baseline and remain unresolved here (fixing them would
  require editing protected release files, which is out of scope).
- **Net new failures introduced by this analysis work: zero.** It edits only
  `tests/test_zone_model_audit.py`, `scripts/*` and `reports/zone-model-audit/*` /
  `data/interim/*`; it never touches `releases/`, canonical data, routing graph, or
  production.
