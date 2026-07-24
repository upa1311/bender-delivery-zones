# Zone / pricing separation contract

> Zones and prices are two independent layers. This repository owns **zones
> only**. It never assigns money, and a consuming product (Direct) must keep the
> two apart.

## The rule

1. **Zone geometry and zone assignment carry no money.** A zone is a distance
   band (K=4, Scenario A) over OSRM road kilometres. The published zone dataset
   contains `zone_id`, geometry, colours and the address → zone mapping, and
   **nothing priced**.

2. **Pricing is a separate layer.** The customer delivery fee and the courier
   payout live in a `Zone X → Zone Y` tariff matrix that is owned and edited in
   Direct, never here. This repo ships the *shape* of that matrix
   (`schemas/zone-tariff-matrix.schema.json`) with every money field `null`.

3. **The zone dataset is versioned and immutable.** Each release
   (`releases/bender-zones-v1/`) is frozen: a manifest pins the
   `source_dataset_version`, the K=4 edges, the file list and SHA-256 checksums.
   A completed order stores an **immutable zone snapshot** (dataset version +
   origin/destination zone), so a later zone or tariff change never rewrites a
   finished order.

4. **Changing zones ≠ changing prices.** Re-releasing zones bumps
   `zone_dataset_version`. It does not touch any tariff row, any `priceCents`,
   any courier payout, or any cash movement. Those change only through Direct's
   own tariff and finance flows.

## What crosses the boundary

| From this repo (zones) | Owned by Direct (money) |
|---|---|
| `zone_id`, zone polygons, colours | `customer_delivery_fee` |
| address → zone resolution | `courier_base_payout` |
| `zone_dataset_version` | `courier_distance_adjustment` |
| Varnița `no_delivery` flag | the whole `Zone X → Zone Y` tariff matrix |
| Северный enclave (Zone 4) | any cash / earnings / settlement amount |

## Guarantees

- No file in `releases/bender-zones-v1/` contains a price, fee, payout or
  currency amount.
- The tariff-matrix schema exists so Direct can attach money later; every value
  is `null` at release time.
- The Direct integration (`docs/zoning-integration.md`, when present) is
  **read-only over zones**: it resolves addresses to zones, shows them in admin
  and to the driver, and snapshots them onto orders — it does not compute or
  modify any monetary amount.
