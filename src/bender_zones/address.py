"""Structured Russian addresses and duplicate street-name disambiguation.

The same street name legitimately exists in several settlements (улица Ленина in
Гиска, Парканы and Бендеры) and sometimes twice inside Бендеры itself. Those are
DIFFERENT streets, not duplicates.

Rules enforced here:

* the real OSM street name is never modified and never has a settlement glued
  into it — ``street_ru`` stays clean;
* settlement, district, street and house number are stored in separate fields;
* a qualifier is added **only for display**, and only when it is needed;
* the tariff zone is never part of an address identity, so re-banding never
  changes which address something is.
"""

from __future__ import annotations

from .normalize import normalize_text

# Territory key -> (settlement, district). Lipcani is a district OF Bender, not a
# separate settlement, so its addresses read "Бендеры, Липканы, ...".
TERRITORY_ADDRESS = {
    "bender_core": ("Бендеры", None),
    "bender_lipcani": ("Бендеры", "Липканы"),
    "giska": ("Гиска", None),
    "parkany": ("Парканы", None),
    "protyagailovka": ("Протягайловка", None),
}

UNKNOWN_SETTLEMENT = "не определён"

# Shown when a street name repeats inside Bender and the other occurrence has no
# district of its own — the spec's "улица Энгельса (Бендеры, другой район)".
OTHER_DISTRICT_SUFFIX = "другой район"


def settlement_district(territory_key: str) -> tuple[str | None, str | None]:
    """Map a territory key to ``(settlement_ru, district_ru)``."""
    return TERRITORY_ADDRESS.get(territory_key, (None, None))


def canonical_address_key(settlement_ru, street_ru, housenumber, district_ru=None,
                          *, district_required: bool = False) -> str | None:
    """Stable identity of a real address.

    ``settlement | district | street | housenumber``, all normalised. The
    district participates only when it is needed to keep two same-named streets
    inside one settlement apart, so an address key never changes just because a
    district label was added elsewhere. The tariff zone is deliberately absent.
    """
    settlement = normalize_text(settlement_ru or "")
    street = normalize_text(street_ru or "")
    number = normalize_text(housenumber or "")
    if not (settlement and street and number):
        return None
    district = normalize_text(district_ru or "") if district_required else ""
    return "|".join([settlement, district, street, number])


def build_street_index(records) -> dict:
    """Decide, per street, whether a display qualifier is needed.

    *records* are ``(settlement_ru, district_ru, street_ru)`` triples. Returns a
    map from that triple to the qualifier to show (``None`` when the street name
    is unique across the whole territory).
    """
    by_name: dict[str, set] = {}
    for settlement, district, street in records:
        if not street:
            continue
        by_name.setdefault(normalize_text(street), set()).add((settlement, district))

    qualifiers: dict = {}
    for _name, places in by_name.items():
        if len(places) == 1:
            settlement, district = next(iter(places))
            qualifiers[(settlement, district, _name)] = None
            continue
        settlements = {s for s, _d in places}
        for settlement, district in places:
            if district:
                # A known district is always more precise than the settlement:
                # "улица Энгельса (Липканы)", never "(Бендеры)".
                qualifiers[(settlement, district, _name)] = district
            elif len(settlements) > 1:
                # Same name in different settlements -> qualify by settlement.
                qualifiers[(settlement, district, _name)] = settlement
            else:
                # Same name twice inside one settlement, this one has no district.
                qualifiers[(settlement, district, _name)] = (
                    f"{settlement}, {OTHER_DISTRICT_SUFFIX}")
    return qualifiers


def display_address_ru(street_ru: str, qualifier: str | None) -> str:
    """Street label for lists, CSV, map popups and search results."""
    street = (street_ru or "").strip()
    if not street:
        return ""
    return f"{street} ({qualifier})" if qualifier else street


def full_address_ru(settlement_ru, district_ru, street_ru, housenumber) -> str:
    """``Гиска, улица Ленина, дом 15`` / ``Бендеры, Липканы, улица Энгельса, дом 24``."""
    parts = [p for p in (settlement_ru, district_ru, (street_ru or "").strip()) if p]
    text = ", ".join(parts)
    number = (housenumber or "").strip()
    return f"{text}, дом {number}" if number else text


def search_variants(query: str, records) -> list[dict]:
    """Search results that keep same-named streets visibly apart.

    *records* are dicts with ``street_ru``/``settlement_ru``/``district_ru``.
    Each result carries the street on one line and its place on another, so
    "Ленина" returns three distinct choices rather than one ambiguous hit.
    """
    needle = normalize_text(query or "")
    if not needle:
        return []
    seen, out = set(), []
    for rec in records:
        street = rec.get("street_ru") or ""
        if needle not in normalize_text(street):
            continue
        key = (rec.get("settlement_ru"), rec.get("district_ru"), normalize_text(street))
        if key in seen:
            continue
        seen.add(key)
        place = ", ".join(p for p in (rec.get("settlement_ru"), rec.get("district_ru"))
                          if p) or UNKNOWN_SETTLEMENT
        out.append({"street_ru": street, "place_ru": place,
                    "settlement_ru": rec.get("settlement_ru"),
                    "district_ru": rec.get("district_ru"),
                    "display_address_ru": rec.get("display_address_ru")
                    or display_address_ru(street, None)})
    out.sort(key=lambda r: (normalize_text(r["street_ru"]), r["place_ru"]))
    return out
