# Test baseline verification — truthful boundary pytest evidence

Documentation/evidence only. No test, release file, immutable hash pin, or production
code is changed by this remediation (the one test edit made by 11afaa7 was reverted
exactly to its f9ad9ca version — see below).

## Canonical baseline (authoritative)

```
Full pytest on START_HEAD 11afaa7: 752 passed, 2 failed, exit code 1.

Final full pytest after the evidence correction: 752 passed, 2 failed, exit code 1.

Failures:
- tests/test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged
- tests/test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged

The same two failures reproduce on START_HEAD 11afaa7. No new failures were introduced.

The change to tests/test_zone_model_audit.py made by 11afaa7 was reverted exactly to
its f9ad9ca version. The cumulative diff from f9ad9ca contains no test changes.
```

The same two failures also reproduce on the preceding commits in the same
verification environment. For example:
`Full pytest on START_HEAD 4d166a3: 751 passed, 2 failed, exit code 1`
(and `9c5b9ca: 750 passed, 2 failed`). No new failures were introduced by any of this
analysis work.

## The two failures: actual vs pinned SHA-256 (MISMATCH)

Both guard tests hash the whole committed `releases/` tree and compare to a pinned
constant. On the canonical clean checkout the actual tree hash does NOT equal the pin,
producing the two failures. Full hashes (not truncated):

**tests/test_router_manual_yandex_evaluator.py::test_immutable_releases_are_unchanged**
(`releases_hash()` over the `releases/` tree)
- pinned : `49edbc87a1f65b2a4c038bd395c5e9880038bf57208c98b9701564135704e9b4`
- actual : `934b0f4abcdb2bffb68e91840aa281848b997c57a14cb79c34a80924d8d44ea7`
- result : **MISMATCH**

**tests/test_yandex_address_inventory_audit.py::test_22_immutable_releases_are_unchanged**
(tree sha over the `releases/` tree, `len(files) == 27`)
- pinned : `f6b666d433dab96d9c71c1a3567d6f9d95b30d07f3b9d7deff3dd05ee08748e2`
- actual : `4bb802224de953435aff2a7a906cf9aa82538df1a913f37dc279708ae431eee4`
- result : **MISMATCH**

The committed protected release files do not match the immutable SHA-256 pins
evaluated by the two guard tests in the canonical (POSIX) checkout. This mismatch
produces the two documented baseline failures. The release files, pins, and tests were
NOT changed by this remediation. The claim `actual == pinned` is false and is not
asserted.

## Cause (established, reproducible — not a CRLF/LF claim)

Both guards hash the tree in `sorted(root.rglob("*"))` order. That sort is over `Path`
objects and is **platform-dependent**: `PosixPath` (Linux/macOS) sorts case-sensitively
(uppercase `IMMUTABLE`/`README.md` before lowercase `data/…`), while `WindowsPath`
sorts case-insensitively. The committed release **content is byte-identical** on every
platform (27 files; no content, pin, or test change); only the concatenation ORDER —
and therefore the tree hash — differs. On the canonical POSIX order the tree hashes to
`934b0f4a…` / `4bb80222…` (≠ pins → the two failures); the pins were recorded on a
Windows-order run (`49edbc87…` / `f6b666d4…`).

Reproducible, platform-independent proof (computes both orders from the committed git
blobs and matches the actual/pinned values above):
`reports/zone-model-audit/_raw/releases-hash-platform-proof.txt`.

## Environment note (why a Windows pytest run differs)

This maintainer environment is Windows-only (Python 3.12.10, pytest 9.1.1; WSL/Docker
unavailable), so a POSIX pytest run that emits the 752/2 summary cannot be executed
here — `WindowsPath` ordering makes the two guards match the pins and pass locally. The
752 passed / 2 failed / exit-1 baseline is therefore established by (a) the reviewer's
independent clean Linux checkout and (b) the deterministic hash proof above, whose
`actual` values equal the reviewer's. The earlier record of a clean full suite with no
failures is superseded and its raw log removed; it is not a valid baseline and the
suite does not pass cleanly on a canonical checkout — exit code is 1.

## Corrections to earlier versions of this note

Earlier versions were wrong and are corrected here:
- an earlier note claimed a clean full run and asserted `actual == pinned`; both were
  false. The mismatch is real (full hashes above).
- the previously named failing tests (`test_release.py`, `test_release_v11.py`) were
  wrong; the actual immutable-release guard failures are the two named above.
- a prior note said "no test is changed" while describing commit 11afaa7's diff; in
  fact 11afaa7 did edit `tests/test_zone_model_audit.py`. That edit has now been
  reverted exactly to its f9ad9ca version, so the cumulative diff from f9ad9ca contains
  no test changes.

## What this analysis work did to the baseline

Nothing. It makes zero changes to `releases/`, to the immutable hash pins, or to the
guard tests. The two immutable-release guard failures are entirely pre-existing and
independent of the owner-boundary packet; this work introduces no new failures.
