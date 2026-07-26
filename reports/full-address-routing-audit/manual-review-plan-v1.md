# Additional manual route plan v1

Canonical registry: `releases/bender-zones-v1.1/address-registry.json` (normalized SHA-256 `bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817`); coordinate join: `docs/data/delivery-units.csv` (normalized SHA-256 `7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250`).

Candidates are clustered by territory, normalized street, corridor, anomaly
family and geographic cell. Every CRITICAL row survives deduplication; other
clusters retain beginning, midpoint, endpoint and worst representative where
distinct.

| priority | selected addresses |
|---|---:|
| CRITICAL | 33 |
| HIGH | 1621 |
| MEDIUM | 494 |

Canonical addresses within 100 m of excluded Varnița: **0**.

- minimum necessary representative set: **970**;
- expanded higher-confidence set: **2148**.

Each selected address and its reason are recorded in
`data/interim/additional-manual-route-candidates-v1.csv`. These are proposals;
no new Yandex measurement was made.
