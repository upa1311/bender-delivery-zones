"""Reference-tariff recompute v2 — DESIGN ONLY, NOT an approved public price.

Implements EXACTLY the owner-corrected model (no 18/6/10, no rounding/ceil):

    base_price(route_km):
        14                       if route_km <= 3
        14 + (route_km - 3) * 4  if route_km  > 3

    external_surcharge(external_km):
        0                        if there is no external part
        max(5, external_km * 2)  if the route crossed the city tariff boundary

    reference_price = base_price + external_surcharge

External rules (per owner): for the Парканы direction the external part starts only
AFTER the ГАИ post on Котовского; distance up to the post is NOT external; the whole
route does not become external retroactively; minimum external surcharge is 5.

BLOCKERS (honest — nothing invented here):
  * The ГАИ post has NO coordinates in the repo
    (data/interim/external-tariff-boundary-anchors-v1.csv → PARKANY_KOTOVSKOGO_GAI_POST
    is OWNER_BRIEF_ONLY, empty lat/lon).
  * The external tariff boundary is not chosen (owner decision pending among OSM
    relations 12463379 / 9581354 / 944727).
  * Per-address route polylines exist for only 12 external addresses (4,338 missing).
So external_km cannot be measured for real addresses → external_surcharge is left
PENDING for external territories, and reference_price there = base_price + PENDING.
City addresses do not cross the boundary → external_surcharge = 0 → reference_price =
base_price (fully computed).

route_km is the canonical central-origin distance and is known to be overstated for
some streets (e.g. Кишинёвская ~6.5–7.2 in data vs ~4.7–4.9 on Yandex; Yandex is not
reachable in this environment). Such streets are flagged.

Zones are formed by the ACTUAL spread of reference_price using 1-D natural breaks
(Jenks) — never equal-km intervals or quartiles. Zones are internal (admin / cost
control / analytics / tariff design); client never sees zone numbers.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OC_SPEC = importlib.util.spec_from_file_location(
    "outside_city_distance", ROOT / "scripts/outside_city_distance.py")
OC = importlib.util.module_from_spec(OC_SPEC)
OC_SPEC.loader.exec_module(OC)

OUT_CSV = ROOT / "data/interim/reference-tariff-v2.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_reference-tariff-v2-summary.json"
REPORT_MD = ROOT / "reports/zone-model-audit/reference-tariff-v2.md"

EXTERNAL_TERRITORIES = ("Парканы", "Гиска", "Протягайловка", "Северный")


def base_price(route_km: float) -> float:
    """14 up to 3 km, then +4 per km beyond 3 km. No rounding."""
    return 14.0 if route_km <= 3.0 else 14.0 + (route_km - 3.0) * 4.0


def external_surcharge(external_km):
    """0 if no external part; else max(5, external_km*2). external_km None => unknown."""
    if external_km is None:
        return None
    if external_km <= 0:
        return 0.0
    return max(5.0, external_km * 2.0)


def reference_price(route_km, external_km):
    b = base_price(route_km)
    s = external_surcharge(external_km)
    return (None if s is None else round(b + s, 3)), round(b, 3), s


# ----------------------- natural breaks (Jenks) -----------------------

def jenks_breaks(values, k):
    """Classic 1-D Jenks natural breaks. Returns k-1 break values (upper edges of
    classes 1..k-1). O(n*k) memory with the standard DP; n≈4866, k≤7 is fine."""
    data = sorted(values)
    n = len(data)
    if k >= n:
        return data[:]
    mat1 = [[0] * (k + 1) for _ in range(n + 1)]
    mat2 = [[0.0] * (k + 1) for _ in range(n + 1)]
    for j in range(1, k + 1):
        mat1[1][j] = 1
        mat2[1][j] = 0.0
        for i in range(2, n + 1):
            mat2[i][j] = float("inf")
    for ln in range(2, n + 1):
        s1 = s2 = wt = 0.0
        for m in range(1, ln + 1):
            i3 = ln - m + 1
            val = data[i3 - 1]
            s2 += val * val
            s1 += val
            wt += 1
            var = s2 - (s1 * s1) / wt
            i4 = i3 - 1
            if i4 != 0:
                for j in range(2, k + 1):
                    if mat2[ln][j] >= var + mat2[i4][j - 1]:
                        mat1[ln][j] = i3
                        mat2[ln][j] = var + mat2[i4][j - 1]
        mat1[ln][1] = 1
        mat2[ln][1] = s2 - (s1 * s1) / wt
    kclass = [0.0] * k
    kclass[k - 1] = data[n - 1]
    kk, idx = n, k
    while idx >= 2:
        boundary = mat1[kk][idx] - 1
        kclass[idx - 2] = data[boundary - 1]
        kk = mat1[kk][idx] - 1
        idx -= 1
    return kclass  # class upper edges; kclass[-1] == max


def gvf(values, breaks):
    """Goodness of variance fit for a Jenks classification (0..1)."""
    data = sorted(values)
    mean = sum(data) / len(data)
    sdam = sum((v - mean) ** 2 for v in data)
    # assign each value to a class by upper edges
    edges = breaks
    classes = {}
    for v in data:
        ci = 0
        while ci < len(edges) - 1 and v > edges[ci]:
            ci += 1
        classes.setdefault(ci, []).append(v)
    sdcm = 0.0
    for arr in classes.values():
        m = sum(arr) / len(arr)
        sdcm += sum((v - m) ** 2 for v in arr)
    return 1.0 - sdcm / sdam if sdam else 1.0


# ----------------------- main -----------------------

def main():
    addrs = OC.ZE.ZM.load_addresses()
    rows = []
    for r in addrs:
        km = r["route_km"]
        settlement = r["settlement"]
        is_city = bool(r.get("is_city")) and settlement not in EXTERNAL_TERRITORIES
        external_km = 0.0 if is_city else None  # city: no external; else UNKNOWN
        ref, base, sur = reference_price(km, external_km)
        addr = ", ".join(str(r[k]) for k in ("settlement", "street", "house") if r.get(k))
        rows.append({
            "uid": r["uid"], "address": addr, "territory": settlement,
            "is_city": is_city, "route_km": round(km, 3),
            "base_price": base,
            "external_status": "n/a (city)" if is_city
            else "PENDING (no ГАИ-post coords + boundary undecided)",
            "external_km": "" if external_km is None else 0.0,
            "external_surcharge": "" if sur is None else sur,
            "reference_price": "" if ref is None else ref,
            "old_k4_zone_id": r.get("zone_id", ""),
        })

    # Zones from the ACTUAL reference_price spread — city addresses only (their
    # reference_price is complete). External territories get a zone once their
    # external surcharge is known.
    city_prices = [row["reference_price"] for row in rows
                   if row["is_city"] and row["reference_price"] != ""]
    k_eval = {}
    for k in range(3, 8):
        br = jenks_breaks(city_prices, k)
        k_eval[k] = {"breaks": [round(b, 3) for b in br], "gvf": round(gvf(city_prices, br), 4)}
    # recommend smallest k whose GVF >= 0.90 (else the k with best marginal gain)
    recommended = next((k for k in range(3, 8) if k_eval[k]["gvf"] >= 0.90), 5)
    rec_breaks = jenks_breaks(city_prices, recommended)

    # assign city rows to recommended zones and describe each zone
    def zone_of(price):
        ci = 0
        while ci < len(rec_breaks) - 1 and price > rec_breaks[ci]:
            ci += 1
        return ci + 1
    zone_stats = {}
    for row in rows:
        if row["is_city"] and row["reference_price"] != "":
            z = zone_of(row["reference_price"])
            row["proposed_zone"] = z
            st = zone_stats.setdefault(z, {"n": 0, "price_min": 1e9, "price_max": -1e9,
                                           "km_min": 1e9, "km_max": -1e9})
            st["n"] += 1
            st["price_min"] = min(st["price_min"], row["reference_price"])
            st["price_max"] = max(st["price_max"], row["reference_price"])
            st["km_min"] = min(st["km_min"], row["route_km"])
            st["km_max"] = max(st["km_max"], row["route_km"])
        else:
            row["proposed_zone"] = ""  # external: pending external surcharge

    for st in zone_stats.values():
        for kf in ("price_min", "price_max", "km_min", "km_max"):
            st[kf] = round(st[kf], 3)

    # Кишинёвская accuracy flag
    kish = [row for row in rows if "Кишинёв" in row["address"]]
    kish_km = sorted({row["route_km"] for row in kish})

    with OUT_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    summary = {
        "model": "reference_tariff_v2 (DESIGN, not approved price)",
        "formula": {
            "base_price": "14 if route_km<=3 else 14 + (route_km-3)*4 (no rounding)",
            "external_surcharge": "0 if no external part else max(5, external_km*2)",
            "reference_price": "base_price + external_surcharge",
            "rejected": "18 / 6 / 10 (taxi-calibration assumption, NOT the tariff)",
        },
        "worked_example_check": _worked_example(),
        "addresses_total": len(rows),
        "city_addresses_priced": len(city_prices),
        "external_addresses_pending": sum(1 for r in rows if not r["is_city"]),
        "base_price_min": round(min(r["base_price"] for r in rows), 3),
        "base_price_max": round(max(r["base_price"] for r in rows), 3),
        "zone_candidates_gvf": k_eval,
        "recommended_zone_count": recommended,
        "recommended_breaks_price": [round(b, 3) for b in rec_breaks],
        "zone_stats": {str(z): zone_stats[z] for z in sorted(zone_stats)},
        "kishinevskaya": {
            "data_route_km_values": kish_km,
            "yandex_expected_km": "≈4.7–4.9",
            "flag": "route_km OVERSTATED vs Yandex; Yandex not reachable in this env",
        },
        "blockers": [
            "ГАИ post on Котовского has no coordinates (external cannot start after it)",
            "external tariff boundary undecided (relations 12463379/9581354/944727)",
            "route polylines missing for 4,338 external addresses",
            "route_km is central-origin, not per-restaurant, and inaccurate for some "
            "streets (Кишинёвская)",
        ],
        "status": "PRELIMINARY DESIGN — external surcharge & external-territory zones "
                  "pending owner inputs; not a public price",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    _write_report(summary)
    print(json.dumps({k: summary[k] for k in
                      ("addresses_total", "city_addresses_priced",
                       "external_addresses_pending", "recommended_zone_count",
                       "recommended_breaks_price")}, ensure_ascii=False))


def _worked_example():
    ref, base, sur = reference_price(7.2, 2.6)
    return {"total_km": 7.2, "external_km": 2.6, "base_price": base,
            "external_surcharge": sur, "reference_price": ref,
            "matches_owner_example_36": round(ref) == 36}


def _write_report(s):
    e = s["worked_example_check"]
    z = s["zone_stats"]
    lines = [
        "# Reference-tariff recompute v2 — DESIGN, not an approved price", "",
        "**Formula (owner-corrected; 18/6/10 rejected):**", "",
        "- base_price = 14 (≤3 км), иначе 14 + (route_km−3)×4 — без округления",
        "- external_surcharge = 0, если нет внешней части; иначе max(5, external_km×2)",
        "- reference_price = base_price + external_surcharge", "",
        f"Проверка примера владельца: 7.2 км → base {e['base_price']}, внешние 2.6 км → "
        f"надбавка {e['external_surcharge']}, итог {e['reference_price']} "
        f"(≈36: {e['matches_owner_example_36']}).", "",
        "## Что посчитано и что заблокировано", "",
        f"- Адресов всего: **{s['addresses_total']}**; городских с полной ценой: "
        f"**{s['city_addresses_priced']}**; внешних территорий (external PENDING): "
        f"**{s['external_addresses_pending']}**.",
        "- Внешняя надбавка НЕ посчитана для внешних территорий: нет координат поста "
        "ГАИ, граница не выбрана, нет polyline для 4 338 адресов. Ничего не выдумано.",
        f"- base_price диапазон: {s['base_price_min']}–{s['base_price_max']} руб.", "",
        "## Кишинёвская — расхождение route_km", "",
        f"route_km в данных: {s['kishinevskaya']['data_route_km_values']} км; ожидаемое "
        f"по Яндексу: {s['kishinevskaya']['yandex_expected_km']} км. route_km завышен; "
        "Яндекс недоступен в этой среде — требует независимой сверки.", "",
        "## Зоны по фактическому разбросу цены (Jenks natural breaks)", "",
        "Не равные интервалы и не квартили. Оценка числа зон по GVF:", "",
        "| зон | GVF | границы цены (руб.) |", "|---:|---:|---|",
    ]
    for k in sorted(s["zone_candidates_gvf"], key=int):
        c = s["zone_candidates_gvf"][k]
        lines.append(f"| {k} | {c['gvf']} | {c['breaks']} |")
    lines += [
        "", f"**Рекомендовано зон: {s['recommended_zone_count']}** "
        f"(границы цены: {s['recommended_breaks_price']}).", "",
        "| зона | адресов | цена руб. (min–max) | route_km (min–max) |",
        "|---:|---:|---|---|",
    ]
    for zid in sorted(z, key=int):
        st = z[zid]
        lines.append(f"| {zid} | {st['n']} | {st['price_min']}–{st['price_max']} | "
                     f"{st['km_min']}–{st['km_max']} |")
    lines += [
        "", "Зоны — внутренние (админ/контроль стоимости/аналитика/настройка "
        "тарифа); клиенту номер зоны не показывается. Внешним территориям зона будет "
        "назначена после расчёта внешней надбавки.", "",
        "## Блокеры (нужны от владельца)", "",
    ]
    for b in s["blockers"]:
        lines.append(f"- {b}")
    lines += ["", "**Статус:** " + s["status"] + ". Старые 4 зоны K4 автоматически "
              "не сохранены и не заменены; это расчётная модель для проектирования.", ""]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
