#!/usr/bin/env python3
"""Interroge le Géoportail de l'urbanisme (API Carto IGN) et le WFS BD TOPO autour du pylône.

Écrit les réponses brutes dans sources/gpu/ (Licence Ouverte 2.0) et met à jour sources/SHA256SUMS.
Ensuite : python3 -I tools/plu_gpu.py  (lit sources/gpu/, écrit antenne-reglement.ttl).
"""
import hashlib, json, math, re, subprocess, sys, datetime
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
OUT = ROOT / "sources" / "gpu"
OUT.mkdir(parents=True, exist_ok=True)
CX, CY = -4.274491, 47.874985          # pylône (POINT du dossier)
R = 800                                  # rayon de la fenêtre interrogée, en mètres
KY = 110540.0
KX = 111320.0 * math.cos(math.radians(CY))

ring = [[CX + R * math.cos(a * math.pi / 32) / KX, CY + R * math.sin(a * math.pi / 32) / KY] for a in range(64)]
ring.append(ring[0])
GEOM = json.dumps({"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}, separators=(",", ":"))

def curl(args):
    out = subprocess.run(["curl", "-sS", "--fail", "--max-time", "90", *args], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"curl : {out.stderr}")
    return out.stdout

files = {}
for ep in ["zone-urba", "prescription-surf", "prescription-lin", "prescription-pct",
           "info-surf", "info-lin", "info-pct", "secteur-cc"]:
    txt = curl(["-G", f"https://apicarto.ign.fr/api/gpu/{ep}", "--data-urlencode", f"geom={GEOM}"])
    json.loads(txt)
    files[f"{ep}.geojson"] = txt

bb = f"{CX - R / KX:.6f},{CY - R / KY:.6f},{CX + R / KX:.6f},{CY + R / KY:.6f},EPSG:4326"
url = ("https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=BDTOPO_V3:troncon_de_route"
       f"&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326&BBOX={bb}&COUNT=500")
files["routes_bdtopo.geojson"] = curl([url])
json.loads(files["routes_bdtopo.geojson"])

sums = {}
for name, txt in files.items():
    (OUT / name).write_text(txt, encoding="utf-8")
    sums[f"gpu/{name}"] = hashlib.sha256(txt.encode()).hexdigest()
meta = {"date": datetime.date.today().isoformat(), "centre": [CX, CY], "rayon_m": R,
        "sources": ["https://apicarto.ign.fr/api/gpu/*", "https://data.geopf.fr/wfs/ows (BDTOPO_V3:troncon_de_route)"]}
(OUT / "FETCH.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

p = ROOT / "sources" / "SHA256SUMS"
keep = [l for l in p.read_text().splitlines() if not re.search(r"\sgpu/", l)]
keep += [f"{h}  {n}" for n, h in sorted(sums.items())]
p.write_text("\n".join(keep) + "\n")
print({n: len(t) for n, t in files.items()})
