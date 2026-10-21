"""Look up terrain elevation along the route from AWS Terrain Tiles (Terrarium PNGs, zoom 15; USGS 3DEP-derived in the US).

Inputs:  data/samples.json, data/bridge_probes.json
Outputs: data/elev_raw.json   metres, one per sample (bilinear)
         data/probe_elev.json {"probes": [...metres], "lynn_st": metres}
Needs internet access and Pillow. Tiles: https://registry.opendata.aws/terrain-tiles/
"""
import io
import json
import math
import urllib.request
from PIL import Image
from config import DATA

Z = 15
URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
LYNN_ST = (38.8990, -77.0712)     # N Lynn St just south of the Key Bridge abutment (Rosslyn end)
_cache = {}


def tile(tx, ty):
    if (tx, ty) not in _cache:
        req = urllib.request.Request(URL.format(z=Z, x=tx, y=ty), headers={'User-Agent': 'marathon-race-viewer'})
        with urllib.request.urlopen(req, timeout=60) as r:
            _cache[(tx, ty)] = Image.open(io.BytesIO(r.read())).convert('RGB').load()
    return _cache[(tx, ty)]


def pixel(lat, lon):
    n = 1 << Z
    s = math.sin(math.radians(lat))
    return (lon + 180) / 360 * n * 256, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n * 256


def height(px, py):
    tx, ty = int(px // 256), int(py // 256)
    r, g, b = tile(tx, ty)[int(px) - tx * 256, int(py) - ty * 256]
    return r * 256 + g + b / 256 - 32768


def bilinear(px, py):
    px, py = px - 0.5, py - 0.5
    x0, y0 = math.floor(px), math.floor(py)
    fx, fy = px - x0, py - y0
    return (height(x0, y0) * (1 - fx) * (1 - fy) + height(x0 + 1, y0) * fx * (1 - fy)
            + height(x0, y0 + 1) * (1 - fx) * fy + height(x0 + 1, y0 + 1) * fx * fy)


if __name__ == '__main__':
    samples = json.load(open(DATA / 'samples.json'))
    probes = json.load(open(DATA / 'bridge_probes.json'))['probes']
    elev = [round(bilinear(*pixel(s[0], s[1])), 1) for s in samples]
    json.dump(elev, open(DATA / 'elev_raw.json', 'w'))
    json.dump({'probes': [round(height(*pixel(*p)), 1) for p in probes], 'lynn_st': round(height(*pixel(*LYNN_ST)), 1)},
              open(DATA / 'probe_elev.json', 'w'))
    print(f"{len(elev)} samples from {len(_cache)} tiles")
