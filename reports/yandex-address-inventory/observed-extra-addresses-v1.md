# Reverse Yandex address audit v1 — PARTIAL

Ten territory/district/street groups received an initial manual reverse review. Every
group remains `PARTIAL`; none is claimed complete because street ends, side branches,
or the full visible numbering range were not all reviewed.

| Metric | Value |
|---|---:|
| Street groups in canonical population | 316 |
| Groups with initial reverse review | 10 |
| COMPLETE_FOR_VISIBLE_MAP groups | 0 |
| Concrete Yandex-only candidates recorded | 7 |
| HIGH-confidence Yandex-only addresses | 1 |
| MEDIUM-confidence candidates | 6 |

The single HIGH-confidence observation is Советская улица 31, Бендеры. It was visible
in two independent manual address searches, has a concrete house number and normal
addressed-building card, and is absent from both the canonical 9,216 and the recovered
candidate address keys. It is an observed lower-bound candidate, not an approved
canonical addition.

The other six observations remain MEDIUM because they have only one independent
search or conflicting facility evidence. Organizations, entrances, apartments, POIs
without addresses, and duplicate organizations at an existing address were not
counted as Yandex-only addresses.

No exact uplift or full Yandex address total is inferred. With 10/316 groups only
partially reviewed, the result remains `PARTIAL_EVIDENCE_ONLY`.
