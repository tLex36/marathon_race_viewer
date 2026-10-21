"""Split road lines at every at-grade crossing (bridges/tunnels noded separately) -> noded_roads.geojson."""
import json
from config import DATA
import shapely
from shapely.geometry import shape, mapping
from shapely.strtree import STRtree

fc = json.load(open(DATA / 'roads.geojson'))
SKIP_KIND = {'rail', 'ferry', 'aerialway'}
groups = {'bridge': [], 'tunnel': [], 'ground': []}
for f in fc['features']:
    p = f['properties']
    if p.get('kind') in SKIP_KIND:
        continue
    lvl = 'bridge' if p.get('is_bridge') else 'tunnel' if p.get('is_tunnel') else 'ground'
    groups[lvl].append((shape(f['geometry']), p))

out = []
for lvl, items in groups.items():
    geoms = [g for g, _ in items]
    tree = STRtree(geoms)
    noded = shapely.node(shapely.GeometryCollection(geoms))
    pieces = list(noded.geoms)
    mids = [shapely.line_interpolate_point(s, 0.5, normalized=True) for s in pieces]
    idx = tree.query_nearest(mids, all_matches=False, return_distance=False)[1]
    for s, i in zip(pieces, idx):
        out.append({"type": "Feature", "properties": {**items[i][1], "level": lvl}, "geometry": mapping(s)})
    print(lvl, len(items), '->', len(pieces))
json.dump({"type": "FeatureCollection", "features": out}, open(DATA / 'noded_roads.geojson', 'w'))
