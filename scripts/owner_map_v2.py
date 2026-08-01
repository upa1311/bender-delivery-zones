"""Full owner boundary map v2 — self-contained, ANALYSIS ONLY.

Renders every mandated layer from committed local data (no external tiles/APIs):
  * OSM relations 12463379 / 9581354 / 944727 (real extracted geometry)
  * repo provisional boundary (source-boundaries.geojson)
  * settlement polygons Парканы / Гиска / Протягайловка / Бендеры
  * Северный service-area polygon + delivery-unit points (candidate, owner_review)
  * all 12 real route polylines
  * ALL 4,350 canonical external address points (embedded, not sampled — canvas)
  * external tariff anchors incl. пост ГАИ на Котовского — shown as UNPROVEN /
    no-coordinates (never plotted as an invented point)

The HTML embeds an automatic self-check comparing expected (4350) vs embedded point
count and renders it on the page. Each boundary/route/point layer toggles separately.
A static PNG preview (all three boundaries in distinct colours) is written too.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
BND = ROOT / "data/interim/osm-boundaries"
DOCS = ROOT / "docs/data"
FEES = ROOT / "data/interim/outside-city-distance-v1.csv"
ANCHORS = ROOT / "data/interim/external-tariff-boundary-anchors-v1.csv"
INVSUM = ROOT / "reports/zone-model-audit/_boundary-scenarios-summary.json"
HTML = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.html"
PNG = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.png"
SVG = ROOT / "reports/zone-model-audit/owner-boundary-map-v2.svg"

EXPECTED_POINTS = 4350
BCOLORS = {"12463379": "#d62828", "9581354": "#1d7874", "944727": "#8338ec"}
SCOLORS = {"parkany": "#7b2cbf", "giska": "#2a9d3f", "protyagailovka": "#f07f14",
           "bender": "#888888"}


def _rings(geom):
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return [list(p.exterior.coords) for p in polys]


def _load_geojson_rings(path, key_field, wanted):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        k = f["properties"].get(key_field)
        if wanted is None or k in wanted:
            out[k] = _rings(shape(f["geometry"]))
    return out


def collect():
    boundaries = {rid: _rings(shape(json.loads(
        (BND / f"relation-{rid}.geojson").read_text(encoding="utf-8"))["geometry"]))
        for rid in ("12463379", "9581354", "944727")}
    repo = _load_geojson_rings(DOCS / "source-boundaries.geojson", "key", {"bender"})
    settle = _load_geojson_rings(DOCS / "settlements.geojson", "key",
                                 {"parkany", "giska", "protyagailovka", "bender"})
    sev_area = _rings(shape(json.loads(
        (DOCS / "severny-service-area.geojson").read_text(encoding="utf-8")
    )["features"][0]["geometry"]))
    sev_units = [f["geometry"]["coordinates"] for f in json.loads(
        (DOCS / "severny-delivery-units.geojson").read_text(encoding="utf-8"))["features"]]
    rows = list(csv.DictReader(FEES.open(encoding="utf-8-sig")))
    pts = [[round(float(r["longitude"]), 5), round(float(r["latitude"]), 5),
            r["territory"]] for r in rows if r["latitude"]]
    # 12 route polylines from the scenario inventory (reuse outside_city_distance)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "oc", ROOT / "scripts/outside_city_distance.py")
    oc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oc)
    reg = {r["uid"]: r for r in oc.ZE.ZM.load_addresses()}
    external = [r for r in reg.values() if r["settlement"] in oc.EXTERNAL_SETTLEMENTS]
    inv, _p, _c, _t = oc.build_inventory(external, reg)
    routes = [[[round(x, 5), round(y, 5)] for x, y in v["coords"]]
              for v in inv.values() if "coords" in v]
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
    # points first (light)
    pcol = {"Парканы": "#c9a0dc", "Гиска": "#9fd8a0", "Протягайловка": "#f5c48a"}
    for x, y, t in d["pts"]:
        px_, py_ = px(x, y)
        dr.ellipse([px_ - 1, py_ - 1, px_ + 1, py_ + 1],
                   fill=pcol.get(t, "#bbbbbb"))
    # three boundaries, distinct colours, drawn as outlines
    for rid, rings in d["boundaries"].items():
        for r in rings:
            dr.line([px(x, y) for x, y in r], fill=BCOLORS[rid], width=3)
    # severny area
    for r in d["sev_area"]:
        dr.line([px(x, y) for x, y in r], fill="#e83e8c", width=2)
    # routes
    for rt in d["routes"]:
        dr.line([px(x, y) for x, y in rt], fill="#1f4e79", width=1)
    dr.rectangle([20, 20, 470, 150], outline="#ccc")
    for i, (t, c) in enumerate([
            ("r12463379 admin_level 8 — city proper (21.0 km2)", BCOLORS["12463379"]),
            ("r9581354 admin_level 4 — municipality (37.7 km2)", BCOLORS["9581354"]),
            ("r944727 admin_level 5 — de-facto PMR (72.0 km2)", BCOLORS["944727"]),
            ("Северный candidate service area (owner_review)", "#e83e8c"),
            ("12 route polylines / 4350 external points", "#1f4e79")]):
        dr.text((30, 30 + i * 22), t, fill=c)
    img.save(PNG)
    # minimal SVG twin (outlines only) for a vector preview
    def sp(r):
        return " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in r)
    segs = []
    for rid, rings in d["boundaries"].items():
        for r in rings:
            segs.append(f'<polyline points="{sp(r)}" fill="none" '
                        f'stroke="{BCOLORS[rid]}" stroke-width="2"/>')
    SVG.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
        f'{"".join(segs)}</svg>', encoding="utf-8", newline="\n")


def build_html(d, bb):
    payload = {
        "bbox": bb, "boundaries": d["boundaries"], "repo": d["repo"],
        "settle": d["settle"], "sevArea": d["sev_area"], "sevUnits": d["sev_units"],
        "routes": d["routes"], "pts": d["pts"], "expected": EXPECTED_POINTS,
        "bcolors": BCOLORS, "scolors": SCOLORS,
    }
    anchors_rows = "".join(
        f"<tr><td>{a['anchor_id']}</td><td>{a['territory']}</td>"
        f"<td>{a['anchor_name']}</td><td>{a['lat'] or '—'}</td>"
        f"<td>{a['lon'] or '—'}</td><td>{a['confidence']}</td></tr>"
        for a in d["anchors"])
    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = _TEMPLATE.replace("__DATA__", data_js).replace("__ANCHORS__", anchors_rows)
    HTML.write_text(html, encoding="utf-8", newline="\n")


_TEMPLATE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Owner boundary map v2 — external tariff (analysis)</title>
<style>
 body{font:14px system-ui;margin:12px;color:#111}
 #wrap{display:flex;gap:16px;flex-wrap:wrap}
 #controls label{display:block;margin:3px 0}
 canvas{border:1px solid #ccc;max-width:100%;height:auto}
 table{border-collapse:collapse;font-size:12px;margin-top:8px}
 td,th{border:1px solid #ddd;padding:2px 6px}
 .warn{color:#b00}
 @media(prefers-color-scheme:dark){body{background:#111;color:#eee}canvas{background:#fff}}
</style></head><body>
<h2>Карта тарифной границы v2 — ANALYSIS, не production</h2>
<p>Три реальные OSM-границы + repo provisional + сёла + Северный (candidate) + 12
маршрутов + <b>все 4 350</b> внешних адресов. Ни одна граница не VERIFIED_FOR_TARIFF.</p>
<div id="wrap">
 <div id="controls">
  <b>Слои</b>
  <label><input type="checkbox" id="L_r12463379" checked> r12463379 (level 8, 21 km²)</label>
  <label><input type="checkbox" id="L_r9581354" checked> r9581354 (level 4, 37.7 km²)</label>
  <label><input type="checkbox" id="L_r944727" checked> r944727 (level 5, 72 km²)</label>
  <label><input type="checkbox" id="L_repo" checked> repo provisional</label>
  <label><input type="checkbox" id="L_settle" checked> сёла (полигоны)</label>
  <label><input type="checkbox" id="L_severny" checked> Северный (candidate)</label>
  <label><input type="checkbox" id="L_routes" checked> 12 маршрутов</label>
  <label><input type="checkbox" id="L_points" checked> 4350 адресов</label>
  <p id="check"></p>
 </div>
 <canvas id="c" width="1000" height="780"></canvas>
</div>
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
  Object.values(D.repo).forEach(rs=>rs.forEach(r=>{ring(r);ctx.stroke();}));ctx.setLineDash([]);}
 [['12463379','L_r12463379'],['9581354','L_r9581354'],['944727','L_r944727']].forEach(([rid,id])=>{
  if(on(id)){ctx.strokeStyle=D.bcolors[rid];ctx.lineWidth=2.5;D.boundaries[rid].forEach(r=>{ring(r);ctx.stroke();});}});
 if(on('L_routes')){ctx.strokeStyle='#1f4e79';ctx.lineWidth=1;
  D.routes.forEach(rt=>{ring(rt);ctx.stroke();});}
}
document.querySelectorAll('#controls input').forEach(e=>e.addEventListener('change',draw));
const emb=D.pts.length;
document.getElementById('check').innerHTML=
 'expected points: '+D.expected+'<br>embedded points: '+emb+'<br>'+
 (emb===D.expected?'<b style=color:green>OK 4350/4350</b>':'<b class=warn>MISMATCH</b>');
draw();
</script></body></html>"""


def main():
    d = collect()
    bb = _bbox(d)
    build_png(d, bb)
    build_html(d, bb)
    print(json.dumps({"points_embedded": len(d["pts"]), "expected": EXPECTED_POINTS,
                      "routes": len(d["routes"]), "boundaries": len(d["boundaries"]),
                      "severny_units": len(d["sev_units"]),
                      "anchors": len(d["anchors"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
