# Stage 09C — route №5 south corridor (OSM match)

**Read-only. No OSM edit, no release, no Direct, no price, no new zone.
owner_review_required. EasyWay web is bot-blocked (HTTP 403) — polyline NOT
fetched, NOT fabricated; the corridor is verified against OSM directly.**

Owner ground truth: bus route №5 runs a southern loop centre → пл. Героев →
Молдплодовощ → Пивзавод → Маслоэкстракционный завод → Ечина → больница → Главана
→ Старого → Юг-2 → Борисовский рынок. This proves a real **southern car corridor**.

OSM match (`docs/data/stage-09c-route5-osm-match.csv`,
`stage-09c-route5-corridor.geojson`): the named streets (Дружбы, Ечина, Главана,
Старого, Кирова, Ленина, Кишинёвская) are present as car ways, connected to the
graph, crossing the rail at the brewery/Ленинский level crossing (see
`khomutyanovka-brewery-corridor.md`). The маршрутка is used only as **proof of car
connectivity** — no stop loops are enforced, and its full length is not used as a
driver route.

Both directions are recorded; the interchange/one-way segments differ forward vs
reverse. The corridor is in the OSRM graph and is, in fact, the path OSRM's
fastest route already takes to the far (Zone 3–4) Khomutyanovka homes.
