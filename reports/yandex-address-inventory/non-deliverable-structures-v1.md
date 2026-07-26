# Non-deliverable structures audit v1 — PARTIAL

## Population evidence

The immutable `bender-zones-v1.1` registry contains 9,216 unique address keys. Its
coordinate join in `docs/data/delivery-units.csv` preserves only two relevant source
classes: 9,078 `addressed_residential_building` rows and 138
`standalone_address_node` rows. It does not preserve detailed OSM building tags for
garage, shed, barn, outbuilding, construction, ruins, or technical structures.

| Classification | Count |
|---|---:|
| DELIVERABLE | 9,078 |
| NON_DELIVERABLE_STRUCTURE | 0 confirmed from retained metadata |
| UNKNOWN_REQUIRES_REVIEW | 138 |
| Total | 9,216 |

## Requested structure counts

| Structure class | Confirmed in the 9,216-row release | Evidence limitation |
|---|---:|---|
| garage / garages / garage box | 0 | Detailed source type was not retained. |
| shed | 0 | Detailed source type was not retained. |
| barn / outbuilding | 0 | Detailed source type was not retained. |
| construction / ruins | 0 | Detailed source type was not retained. |
| technical structure | 0 | Detailed source type was not retained. |
| unclear object | 138 | Address nodes do not establish a building type. |

Zero means “not confirmed by the retained evidence,” not proof that the canonical
population contains no such structure. The 138 unclear rows remain in the audit and
were not deleted. Excluding confirmed non-deliverable structures therefore changes
the count by zero at this checkpoint; excluding the unclear rows would be unsupported.

Three sampled address nodes were inspected in the visible Yandex Maps interface. All
three opened address-building cards and none was labelled as a garage or shed. This
small observation does not resolve the remaining 135 unclear rows.

No canonical file or immutable release was changed.
