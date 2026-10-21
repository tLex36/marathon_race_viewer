"""Decode OSM road geometry (with names) from the z15 tiles of the extract -> roads.geojson."""
import gzip, json, math, sys
import mapbox_vector_tile as mvt
from config import BASEMAP_BIN, DATA
from slim import tiles_from
from shapely.geometry import shape, box, mapping, LineString, MultiLineString

def tile2lon(x, z): return x / (1 << z) * 360 - 180
def tile2lat(y, z): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << z)))))

src = sys.argv[1] if len(sys.argv) > 1 else str(BASEMAP_BIN)
feats = []
Z = 15
for (z, x, y), data in tiles_from(src):
    if z != Z:
        continue
    t = mvt.decode(gzip.decompress(data))
    lay = t.get('roads')
    if not lay:
        continue
    ext = lay['extent']
    w, e = tile2lon(x, z), tile2lon(x + 1, z)
    n, s = tile2lat(y, z), tile2lat(y + 1, z)
    # convert tile coords (y up after mapbox_vector_tile's default flip) to lon/lat via mercator interpolation
    def conv(px, py):
        fx = px / ext
        fy = 1 - py / ext            # mapbox_vector_tile flips y so origin is bottom-left
        lon = w + (e - w) * fx
        my = (y + fy * 0) if False else None
        ty = y + (1 - (py / ext))    # global tile-y in fractional tiles (top = y)
        ty = y + 1 - py / ext
        return lon, tile2lat(ty, z)
    tb = box(w, s, e, n)
    for f in lay['features']:
        g = f['geometry']
        if g['type'] not in ('LineString', 'MultiLineString'):
            continue
        lines = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
        for ln in lines:
            ll = LineString([conv(px, py) for px, py in ln])
            cl = ll.intersection(tb)
            if cl.is_empty:
                continue
            parts = [cl] if cl.geom_type == 'LineString' else [p for p in getattr(cl, 'geoms', []) if p.geom_type == 'LineString']
            for p in parts:
                if p.length > 0:
                    feats.append({"type": "Feature", "properties": f['properties'], "geometry": mapping(p)})
json.dump({"type": "FeatureCollection", "features": feats}, open(DATA / 'roads.geojson', 'w'))
print(len(feats), "road pieces")
