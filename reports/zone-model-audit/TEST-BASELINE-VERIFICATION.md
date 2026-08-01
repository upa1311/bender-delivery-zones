# Test baseline verification — correction note

This note corrects an earlier inaccurate test summary and records the honest,
independently-checked pytest baseline. It changes no code and fixes no baseline
failure by editing protected release files.

## Correction of the false record

An earlier report and the commit message of `9c5b9ca` stated **"752 passed, 0
failed"** and implied all tests pass. That number is **not** the correct baseline
summary and must not be read as "all tests pass":

- `752` is the TOTAL number of tests. On a checkout that converts line endings, the
  immutable-release / vendored-checksum tests FAIL, so the correct split is
  `N passed + 2 failed` (reviewer's canonical checkout), never `752 passed, 0 failed`.
- Writing `752 passed` collapsed `passed + failed` into a single "passed" figure and
  hid the two pre-existing baseline failures. That is corrected here.

## Mandated baseline formulation (reviewer's canonical checkout)

> **Full pytest on START_HEAD 9c5b9ca: 750 passed, 2 failed. Both failures are the
> existing immutable-release baseline failures; no new failures were introduced.**

The two immutable-release baseline failures are:

- `tests/test_release.py::test_release_checksums_match`
- `tests/test_release_v11.py::test_checksums_match_and_manifest_agrees`

## Why the failing COUNT varies by checkout (root cause)

Every one of these failures is a **line-ending artifact**, not a logic error: the
committed `CHECKSUMS.sha256` manifests are keyed to the **LF** bytes of the release
data files (proven: `sha256(LF bytes) == committed checksum != sha256(CRLF bytes)`).
When git checks those files out with CRLF (Git-for-Windows default `core.autocrlf=
true`), the on-disk bytes differ and the checksum tests fail. How MANY fail depends
purely on how many files a given git converts (its per-file text auto-detection):

| checkout | passed | failed | failing tests |
|---|---:|---:|---|
| reviewer's canonical checkout | 750 | 2 | the two immutable-release tests above |
| this repo, `core.autocrlf=false` (LF) | 752 | 0 | none (release files stay LF) |
| fresh clone, `core.autocrlf=true` (CRLF) | 745 | 7 | the 7 below |

The full CRLF-sensitive set (superset of the reviewer's 2):

- `tests/test_release.py::test_release_checksums_match`
- `tests/test_release.py::test_manifest_file_hashes_match_disk`
- `tests/test_release.py::test_referenced_artifacts_are_checksummed`
- `tests/test_release_v11.py::test_checksums_match_and_manifest_agrees`
- `tests/test_lipcani_classification.py::test_immutable_releases_still_carry_their_own_checksums`
- `tests/test_bands.py::test_car_lua_is_vendored_and_checksummed`
- `tests/test_bands.py::test_build_record_matches_the_vendored_pin`

In every case the total is 752 (750+2 = 745+7 = 752+0).

## Pre-existing, not introduced by this work

All of these failures reproduce on **START_HEAD 9c5b9ca**, on its parent **6d4679c**,
and on **2191d8f** — they predate this analysis layer entirely (they live in
`test_release*.py`, `test_bands.py`, `test_lipcani_classification.py`, none of which
this work touches). This work only edits `tests/test_zone_model_audit.py`.

One line-ending-fragile test that WAS briefly introduced by this work
(`test_zone_model_audit.py::test_118`, added at 6d4679c, which hashed geojson bytes
exactly) was fixed at 9c5b9ca to normalise CRLF→LF before hashing, so it no longer
adds a failure on any checkout. **Net new failures from this work: zero.**

These baseline failures are NOT fixed here: doing so would require editing protected
release files, which is out of scope. They are reported honestly and left as-is.
