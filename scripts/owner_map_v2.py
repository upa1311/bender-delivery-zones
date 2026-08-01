"""Full owner boundary map v2 — self-contained, ANALYSIS ONLY.

Renders every mandated layer from committed local data (no external tiles/APIs):
  * OSM relations 12463379 / 9581354 / 944727 (real extracted geometry)
  * repo provisional boundary (source-boundaries.geojson)
  * settlement polygons Парканы / Гиска / Протягайловка / Бендеры
  * Северный service-area polygon + delivery-unit points (candidate, owner_review)
  * 12 real route polylines, EACH INDEPENDENTLY TOGGLEABLE with a stable route_id,
    click-to-inspect side panel (address, route_km, polyline km, per-boundary
    inside/outside + outside_city_km + surcharge + final fee + fee diff + crossings)
  * ALL 4,350 canonical external address points (embedded, not sampled)
  * disputed routes (price/classification changes across boundaries) highlighted
  * an owner-facing summary table Route × Boundary A/B/C × fee difference
  * external tariff anchors incl. пост ГАИ на Котовского (UNPROVEN, no coords —
    never plotted as an invented point)

Per-route scenario values come from boundary-route-scenarios-v2.csv. The HTML embeds
an automatic self-check comparing expected (4350) vs embedded point count.
A static PNG preview labels the key/ disputed addresses.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
BND = ROOT / "data/interim/osm-boundaries"
DOCS = ROOT / "docs/data"
FEES = ROOT / "data/interim/outside-city-distance-v1.csv"
SCEN = ROOT / "data/interim/boundary-route-scenarios-v2.csv"
ANCHORS = ROOT / "data/interim/external-tariff-boundary-anchors-v1.csv"
HTML = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.html"
PNG = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.png"
SVG = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.svg"

EXPECTED_POINTS = 4350
CANDS = ["12463379", "9581354", "944727"]
BCOLORS = {"12463379": "#d62828", "9581354": "#1d7874", "944727": "#8338ec"}
SCOLORS = {"parkany": "#7b2cbf", "giska": "#2a9d3f", "protyagailovka": "#f07f14",
           "bender": "#888888"}


def _rings(geom):
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return [list(p.exterior.coords) for p in polys]


def _load_rings(path, key_field, wanted):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        k = f["properties"].get(key_field)
        if wanted is None or k in wanted:
            out[k] = _rings(shape(f["geometry"]))
    return out


def _routes_with_scenarios():
    spec = importlib.util.spec_from_file_location(
        "oc", ROOT / "scripts/outside_city_distance.py")
    oc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oc)
    reg = {r["uid"]: r for r in oc.ZE.ZM.load_addresses()}
    external = [r for r in reg.values() if r["settlement"] in oc.EXTERNAL_SETTLEMENTS]
    inv, _p, _c, _t = oc.build_inventory(external, reg)
    scen = list(csv.DictReader(SCEN.open(encoding="utf-8-sig")))
    by_uid = {}
    for r in scen:
        by_uid.setdefault(r["canonical_address_id"], {})[r["boundary_id"]] = r
    routes = []
    for uid, v in inv.items():
        if "coords" not in v or uid not in by_uid:
            continue
        srows = by_uid[uid]
        any_row = next(iter(srows.values()))
        per = {}
        for rid in CANDS:
            s = srows[rid]
            per[rid] = {"inside": s["destination_classification"] == "inside_city",
                        "outside_km": float(s["outside_city_km"]),
                        "surcharge": int(s["geometric_external_surcharge"]),
                        "final": int(s["geometric_final_fee"]),
                        "crossings": int(s["n_crossings"]),
                        "touching": s["touching_boundary"] == "True",
                        "exits": int(s["exits"]), "reentries": int(s["reentries"])}
        finals = [per[r]["final"] for r in CANDS]
        disputed = (min(finals) != max(finals)
                    or any(srows[r]["label_geometry_conflict"] == "True" for r in CANDS))
        routes.append({
            "route_id": f"route_{uid}", "uid": uid,
            "address": any_row["address"], "territory": any_row["territory"],
            "route_km": float(any_row["canonical_route_km"]),
            "polyline_km": float(any_row["polyline_length_km"]),
            "coords": [[round(x, 5), round(y, 5)] for x, y in v["coords"]],
            "per": per, "fee_min": min(finals), "fee_max": max(finals),
            "fee_diff": max(finals) - min(finals), "disputed": disputed,
            "label_conflict": any(srows[r]["label_geometry_conflict"] == "True"
                                  for r in CANDS)})
    routes.sort(key=lambda r: r["uid"])
    return routes


def collect():
    boundaries = {rid: _rings(shape(json.loads(
        (BND / f"relation-{rid}.geojson").read_text(encoding="utf-8"))["geometry"]))
        for rid in CANDS}
    repo = _load_rings(DOCS / "source-boundaries.geojson", "key", {"bender"})
    settle = _load_rings(DOCS / "settlements.geojson", "key",
                         {"parkany", "giska", "protyagailovka", "bender"})
    sev_area = _rings(shape(json.loads(
        (DOCS / "severny-service-area.geojson").read_text(encoding="utf-8")
    )["features"][0]["geometry"]))
    sev_units = [f["geometry"]["coordinates"] for f in json.loads(
        (DOCS / "severny-delivery-units.geojson").read_text(encoding="utf-8"))["features"]]
    rows = list(csv.DictReader(FEES.open(encoding="utf-8-sig")))
    pts = [[round(float(r["longitude"]), 5), round(float(r["latitude"]), 5),
            r["territory"]] for r in rows if r["latitude"]]
    routes = _routes_with_scenarios()
    anchors = list(csv.DictReader(ANCHORS.open(encoding="utf-8-sig")))
    return dict(boundaries=boundaries, repo=repo, settle=settle, sev_area=sev_area,
                sev_units=sev_units, pts=pts, routes=routes, anchors=anchors)


def _bbox(d):
    xs, ys = [], []
    for rings in list(d["boundaries"].values()):
        for r in rings:
            xs += [c[0] for c in r]
            ys += [c[1] for c in r]
    for x, y, _t in d["pts"]:
        xs.append(x)
        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def build_png(d, bb):
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        return
    W, H, M = 1000, 780, 30
    x0, y0, x1, y1 = bb
    s = min((W - 2 * M) / (x1 - x0), (H - 2 * M) / (y1 - y0))

    def px(x, y):
        return (M + (x - x0) * s, H - M - (y - y0) * s)
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    pcol = {"Парканы": "#c9a0dc", "Гиска": "#9fd8a0", "Протягайловка": "#f5c48a"}
    for x, y, t in d["pts"]:
        px_, py_ = px(x, y)
        dr.ellipse([px_ - 1, py_ - 1, px_ + 1, py_ + 1], fill=pcol.get(t, "#bbbbbb"))
    for rid, rings in d["boundaries"].items():
        for r in rings:
            dr.line([px(x, y) for x, y in r], fill=BCOLORS[rid], width=3)
    for r in d["sev_area"]:
        dr.line([px(x, y) for x, y in r], fill="#e83e8c", width=2)
    for rt in d["routes"]:
        col = "#d00000" if rt["disputed"] else "#1f4e79"
        wdt = 2 if rt["disputed"] else 1
        dr.line([px(x, y) for x, y in rt["coords"]], fill=col, width=wdt)
    # label the two price-change addresses (ASCII so the default PIL font renders it)
    labels = [(29.456640, 46.786060, "Giska, Gospitalnaya 8 (34->28)"),
              (29.408, 46.828, "Protyagailovka, Banny per. 1 (35->30)")]
    for rt in d["routes"]:
        if "Госпитальная" in rt["address"] and rt["fee_diff"] > 0:
            labels[0] = (rt["coords"][-1][0], rt["coords"][-1][1],
                         "Giska, Gospitalnaya 8 (34->28)")
        if "Банный" in rt["address"] and rt["fee_diff"] > 0:
            labels[1] = (rt["coords"][-1][0], rt["coords"][-1][1],
                         "Protyagailovka, Banny per. 1 (35->30)")
    for lon, lat, txt in labels:
        p = px(lon, lat)
        dr.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], outline="#d00000", width=2)
        dr.text((p[0] + 5, p[1] - 6), txt, fill="#a00000")
    dr.rectangle([20, 20, 520, 172], outline="#ccc")
    for i, (t, c) in enumerate([
            ("r12463379 admin_level 8 — city proper (21.0 km2)", BCOLORS["12463379"]),
            ("r9581354 admin_level 4 — de-jure municipality (37.7 km2)",
             BCOLORS["9581354"]),
            ("r944727 admin_level 5 — de-facto PMR city (72.0 km2)", BCOLORS["944727"]),
            ("Северный candidate service area (owner_review)", "#e83e8c"),
            ("12 routes: blue=stable, RED=disputed (price/class change)", "#d00000"),
            ("4350 external address points; ⊙ = price-change address", "#333333")]):
        dr.text((30, 30 + i * 22), t, fill=c)
    img.save(PNG)

    def sp(r):
        return " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in r)
    segs = []
    for rid, rings in d["boundaries"].items():
        for r in rings:
            segs.append(f'<polyline points="{sp(r)}" fill="none" '
                        f'stroke="{BCOLORS[rid]}" stroke-width="2"/>')
    for rt in d["routes"]:
        if rt["disputed"]:
            segs.append(f'<polyline points="{sp(rt["coords"])}" fill="none" '
                        f'stroke="#d00000" stroke-width="2"/>')
    SVG.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
        f'{"".join(segs)}</svg>', encoding="utf-8", newline="\n")


def _summary_table(routes):
    rows = ["<tr><th>Route</th><th>Address</th><th>A r12463379</th>"
            "<th>B r9581354</th><th>C r944727</th><th>Δ fee</th></tr>"]
    for rt in sorted(routes, key=lambda r: (-r["fee_diff"], r["uid"])):
        cls = ' class="disp"' if rt["disputed"] else ""
        rows.append(
            f'<tr{cls}><td>{rt["route_id"]}</td><td>{rt["address"]}</td>'
            f'<td>{rt["per"]["12463379"]["final"]}</td>'
            f'<td>{rt["per"]["9581354"]["final"]}</td>'
            f'<td>{rt["per"]["944727"]["final"]}</td><td>{rt["fee_diff"]}</td></tr>')
    return "".join(rows)


def build_html(d, bb):
    payload = {"bbox": bb, "boundaries": d["boundaries"], "repo": d["repo"],
               "settle": d["settle"], "sevArea": d["sev_area"],
               "sevUnits": d["sev_units"], "routes": d["routes"], "pts": d["pts"],
               "expected": EXPECTED_POINTS, "bcolors": BCOLORS, "scolors": SCOLORS}
    route_toggles = "".join(
        f'<label class="{"disp" if rt["disputed"] else ""}">'
        f'<input type="checkbox" class="rt" data-id="{rt["route_id"]}" checked> '
        f'{rt["route_id"]} · {rt["address"]}{" ⚠" if rt["disputed"] else ""}</label>'
        for rt in d["routes"])
    anchors_rows = "".join(
        f"<tr><td>{a['anchor_id']}</td><td>{a['territory']}</td>"
        f"<td>{a['anchor_name']}</td><td>{a['lat'] or '—'}</td>"
        f"<td>{a['lon'] or '—'}</td><td>{a['confidence']}</td></tr>"
        for a in d["anchors"])
    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = (_TEMPLATE.replace("__DATA__", data_js)
            .replace("__ROUTE_TOGGLES__", route_toggles)
            .replace("__SUMMARY__", _summary_table(d["routes"]))
            .replace("__ANCHORS__", anchors_rows))
    HTML.write_text(html, encoding="utf-8", newline="\n")


_TEMPLATE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Owner boundary map v2 — external tariff (analysis)</title>
<style>
 body{font:14px system-ui;margin:12px;color:#111}
 #wrap{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
 #controls{max-width:330px}
 #routes{max-height:220px;overflow:auto;border:1px solid #eee;padding:4px}
 #controls label{display:block;margin:2px 0;font-size:12px}
 label.disp{color:#b00;font-weight:bold}
 canvas{border:1px solid #ccc;max-width:100%;height:auto;cursor:crosshair}
 #side{min-width:260px;max-width:340px;font-size:12px;border:1px solid #ddd;padding:8px}
 table{border-collapse:collapse;font-size:12px;margin-top:8px}
 td,th{border:1px solid #ddd;padding:2px 6px}
 tr.disp{background:#ffecec}
 .warn{color:#b00}
 @media(prefers-color-scheme:dark){body{background:#111;color:#eee}canvas{background:#fff}}
</style></head><body>
<h2>Карта тарифной границы v2 — ANALYSIS, не production</h2>
<p>Три реальные OSM-границы + repo provisional + сёла + Северный (candidate) + 12
маршрутов (каждый переключается отдельно, клик по маршруту — детали) +
<b>все 4 350</b> внешних адресов. Красным — спорные маршруты (цена/классификация
меняется между границами). Ни одна граница не VERIFIED_FOR_TARIFF.</p>
<div id="wrap">
 <div id="controls">
  <b>Границы / слои</b>
  <label><input type="checkbox" id="L_r12463379" checked> r12463379 (level 8, 21 km²)</label>
  <label><input type="checkbox" id="L_r9581354" checked> r9581354 (level 4, 37.7 km²)</label>
  <label><input type="checkbox" id="L_r944727" checked> r944727 (level 5, 72 km²)</label>
  <label><input type="checkbox" id="L_repo" checked> repo provisional</label>
  <label><input type="checkbox" id="L_settle" checked> сёла (полигоны)</label>
  <label><input type="checkbox" id="L_severny" checked> Северный (candidate)</label>
  <label><input type="checkbox" id="L_points" checked> 4350 адресов</label>
  <p id="check"></p>
  <b>Маршруты (каждый отдельно)</b>
  <label><input type="checkbox" id="L_allroutes" checked> все / ни одного</label>
  <div id="routes">__ROUTE_TOGGLES__</div>
 </div>
 <canvas id="c" width="1000" height="780"></canvas>
 <div id="side"><b>Клик по маршруту</b><br>Здесь появятся адрес, route_km, длина
  polyline и цена по каждой границе (A/B/C), разница и пересечения.</div>
</div>
<h3>Сводная таблица: маршруты × границы</h3>
<p>A = r12463379 (город, 21 км²) · B = r9581354 (муниципий, 37.7 км²) ·
C = r944727 (де-факто ПМР, 72 км²). Красные строки — спорные.</p>
<table><tbody>__SUMMARY__</tbody></table>
<h3>Внешние тарифные якоря (в т.ч. пост ГАИ на Котовского)</h3>
<p class="warn">Пост ГАИ и корридоры НЕ имеют координат в данных (OWNER_BRIEF_ONLY,
UNPROVEN) — не наносятся как выдуманные точки.</p>
<table><tr><th>anchor</th><th>территория</th><th>название</th><th>lat</th><th>lon</th>
<th>confidence</th></tr>__ANCHORS__</table>
<script>
const D=__DATA__;
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
const[bx0,by0,bx1,by1]=D.bbox,M=30,W=cv.width,H=cv.height;
const s=Math.min((W-2*M)/(bx1-bx0),(H-2*M)/(by1-by0));
function P(x,y){return[M+(x-bx0)*s,H-M-(y-by0)*s];}
function ring(r){ctx.beginPath();r.forEach((c,i)=>{const p=P(c[0],c[1]);
 i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});}
function on(id){return document.getElementById(id).checked;}
const routeOn={};D.routes.forEach(r=>routeOn[r.route_id]=true);
function draw(){
 ctx.clearRect(0,0,W,H);
 if(on('L_points')){
  const pc={'Парканы':'#c9a0dc','Гиска':'#9fd8a0','Протягайловка':'#f5c48a'};
  D.pts.forEach(p=>{const q=P(p[0],p[1]);
   ctx.fillStyle=pc[p[2]]||'#bbb';ctx.fillRect(q[0],q[1],1.4,1.4);});}
 if(on('L_settle')){Object.entries(D.settle).forEach(([k,rs])=>{
  ctx.strokeStyle=D.scolors[k]||'#999';ctx.setLineDash([4,3]);ctx.lineWidth=1;
  rs.forEach(r=>{ring(r);ctx.stroke();});ctx.setLineDash([]);});}
 if(on('L_severny')){ctx.strokeStyle='#e83e8c';ctx.lineWidth=2;
  D.sevArea.forEach(r=>{ring(r);ctx.stroke();});ctx.fillStyle='#e83e8c';
  D.sevUnits.forEach(u=>{const q=P(u[0],u[1]);ctx.fillRect(q[0]-1,q[1]-1,2.4,2.4);});}
 if(on('L_repo')){ctx.strokeStyle='#000';ctx.lineWidth=1;ctx.setLineDash([2,2]);
  Object.values(D.repo).forEach(rs=>rs.forEach(r=>{ring(r);ctx.stroke();}));
  ctx.setLineDash([]);}
 [['12463379','L_r12463379'],['9581354','L_r9581354'],['944727','L_r944727']]
  .forEach(([rid,id])=>{if(on(id)){ctx.strokeStyle=D.bcolors[rid];ctx.lineWidth=2.5;
   D.boundaries[rid].forEach(r=>{ring(r);ctx.stroke();});}});
 D.routes.forEach(rt=>{if(!routeOn[rt.route_id])return;
  ctx.strokeStyle=rt.disputed?'#d00000':'#1f4e79';ctx.lineWidth=rt.disputed?2.4:1.1;
  ring(rt.coords);ctx.stroke();
  const e=P(rt.coords[rt.coords.length-1][0],rt.coords[rt.coords.length-1][1]);
  if(rt.disputed){ctx.strokeStyle='#d00000';ctx.beginPath();
   ctx.arc(e[0],e[1],3,0,6.28);ctx.stroke();}});
}
function showRoute(rt){
 const p=rt.per,ce=(x)=>x.inside?'город':'вне ('+x.outside_km.toFixed(2)+'км)';
 document.getElementById('side').innerHTML=
  '<b>'+rt.route_id+'</b><br>'+rt.address+' ('+rt.territory+')<br>'+
  'canonical route_km: '+rt.route_km+'<br>polyline km: '+rt.polyline_km+'<br><hr>'+
  '<b>A r12463379</b>: '+ce(p['12463379'])+' → surcharge '+p['12463379'].surcharge+
  ', final '+p['12463379'].final+'<br>'+
  '<b>B r9581354</b>: '+ce(p['9581354'])+' → surcharge '+p['9581354'].surcharge+
  ', final '+p['9581354'].final+'<br>'+
  '<b>C r944727</b>: '+ce(p['944727'])+' → surcharge '+p['944727'].surcharge+
  ', final '+p['944727'].final+'<br><hr>'+
  'Δ fee A..C: <b>'+rt.fee_diff+'</b>'+(rt.disputed?' ⚠ DISPUTED':'')+
  (rt.label_conflict?'<br>label↔geometry conflict (Гиска метка vs полигон)':'')+
  '<br>crossings A: '+p['12463379'].crossings+', touching '+p['12463379'].touching+
  ', exits '+p['12463379'].exits+', reentries '+p['12463379'].reentries;
}
cv.addEventListener('click',ev=>{
 const r=cv.getBoundingClientRect(),mx=(ev.clientX-r.left)*W/r.width,
  my=(ev.clientY-r.top)*H/r.height;let best=null,bd=1e9;
 D.routes.forEach(rt=>{if(!routeOn[rt.route_id])return;rt.coords.forEach(c=>{
  const p=P(c[0],c[1]),dd=(p[0]-mx)**2+(p[1]-my)**2;if(dd<bd){bd=dd;best=rt;}});});
 if(best&&bd<400)showRoute(best);
});
document.querySelectorAll('#controls input:not(.rt)').forEach(e=>{
 if(e.id!=='L_allroutes')e.addEventListener('change',draw);});
document.querySelectorAll('.rt').forEach(cb=>cb.addEventListener('change',()=>{
 routeOn[cb.dataset.id]=cb.checked;draw();}));
document.getElementById('L_allroutes').addEventListener('change',e=>{
 document.querySelectorAll('.rt').forEach(cb=>{cb.checked=e.target.checked;
  routeOn[cb.dataset.id]=cb.checked;});draw();});
const emb=D.pts.length;
document.getElementById('check').innerHTML='expected points: '+D.expected+
 '<br>embedded points: '+emb+'<br>'+
 (emb===D.expected?'<b style=color:green>OK 4350/4350</b>':'<b class=warn>MISMATCH</b>');
draw();
</script></body></html>"""


def main():
    d = collect()
    bb = _bbox(d)
    build_png(d, bb)
    build_html(d, bb)
    disputed = [r["route_id"] for r in d["routes"] if r["disputed"]]
    print(json.dumps({"points_embedded": len(d["pts"]), "expected": EXPECTED_POINTS,
                      "routes": len(d["routes"]), "route_toggles": len(d["routes"]),
                      "disputed_routes": len(disputed),
                      "boundaries": len(d["boundaries"]),
                      "severny_units": len(d["sev_units"]),
                      "anchors": len(d["anchors"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
