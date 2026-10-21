"""Extract Metrorail lines (coloured by line) and stations from the z15 OSM tiles -> metro.geojson."""
import gzip, json, math, re, sys
import mapbox_vector_tile as mvt
from shapely.geometry import LineString, Point, box as sbox, mapping, MultiLineString
from shapely.ops import linemerge, unary_union
from config import DATA, BASEMAP_BIN
from slim import tiles_from

BOX = json.load(open(DATA / 'newbox.json'))
LINES = ['Red', 'Orange', 'Silver', 'Blue', 'Yellow', 'Green']
# Lines serving each station (WMATA service as of Oct 2026; Yellow runs to Greenbelt on alternate trains since Dec 31, 2025)
OSB = ['Orange', 'Silver', 'Blue']
STATION_LINES = {
    **{n: ['Red'] for n in ['Union Station', 'NoMa–Gallaudet U', 'Rhode Island Avenue–Brentwood', 'Brookland–CUA',
                            'Judiciary Square', 'Farragut North', 'Dupont Circle', 'Woodley Park', 'Cleveland Park',
                            'Van Ness–UDC', 'Tenleytown–AU']},
    **{n: OSB for n in ['Rosslyn', 'Foggy Bottom–GWU', 'Farragut West', 'McPherson Square', 'Federal Triangle', 'Smithsonian',
                        'Federal Center Southwest', 'Federal Center SW', 'Capitol South', 'Eastern Market', 'Potomac Avenue']},
    **{n: ['Orange', 'Silver'] for n in ['Court House', 'Clarendon', 'Virginia Square–GMU', 'Ballston–MU']},
    **{n: ['Blue', 'Yellow'] for n in ['Pentagon', 'Pentagon City', 'Crystal City', 'Ronald Reagan Washington National Airport',
                                      'Potomac Yard', 'Braddock Road']},
    **{n: ['Green', 'Yellow'] for n in ['Archives', 'Mount Vernon Square', 'Shaw–Howard University', 'U Street',
                                       'Columbia Heights', 'Georgia Avenue–Petworth']},
    **{n: ['Green'] for n in ['Waterfront', 'Navy Yard–Ballpark', 'Anacostia']},
    'Arlington Cemetery': ['Blue'],
    'Metro Center': ['Red'] + OSB, 'Gallery Place': ['Red', 'Green', 'Yellow'], 'Fort Totten': ['Red', 'Green', 'Yellow'],
    "L'Enfant Plaza": OSB + ['Yellow', 'Green'],
}
ALIASES = {"L'Enfant": "L'Enfant Plaza"}
NOT_METRO = {'Dirksen', 'Hart', 'Rayburn', 'Russell', 'U.S. Capitol', 'Washington Union Station'}  # Capitol subway / Amtrak

def t2lon(x, z): return x / (1 << z) * 360 - 180
def t2lat(y, z): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << z)))))

def lines_of(name):
    if not name or 'Metro' not in name:
        return []
    return [l for l in LINES if re.search(l, name)]

def main(src):
    segs = {l: [] for l in LINES}
    stations = {}
    for (z, x, y), data in tiles_from(src):
        if z != 15:
            continue
        w, e, n, s = t2lon(x, z), t2lon(x + 1, z), t2lat(y, z), t2lat(y + 1, z)
        if e < BOX[0] or w > BOX[2] or n < BOX[1] or s > BOX[3]:
            continue
        t = mvt.decode(gzip.decompress(data))
        conv = lambda px, py, ext: (w + (e - w) * px / ext, t2lat(y + 1 - py / ext, z))
        tb = sbox(w, s, e, n)
        lay = t.get('roads')
        if lay:
            for f in lay['features']:
                p = f['properties']
                ls = lines_of(p.get('name'))
                if p.get('kind_detail') != 'subway' or not ls:
                    continue
                g = f['geometry']
                parts = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
                for part in parts:
                    geom = LineString([conv(px, py, lay['extent']) for px, py in part]).intersection(tb)
                    for gg in ([geom] if geom.geom_type == 'LineString' else getattr(geom, 'geoms', [])):
                        if gg.geom_type == 'LineString' and gg.length > 0:
                            for l in ls:
                                segs[l].append(gg)
        lay = t.get('pois')
        if lay:
            for f in lay['features']:
                p = f['properties']
                if p.get('kind') != 'station' or not p.get('name') or p['name'] in NOT_METRO:
                    continue
                if f['geometry']['type'] != 'Point':
                    continue
                lon, lat = conv(*f['geometry']['coordinates'], lay['extent'])
                stations.setdefault(ALIASES.get(p['name'], p['name']), []).append((lon, lat))
    segs['Silver'] = segs['Silver'] + segs['Orange']   # Silver shares all Orange track inside the map area
    feats = []
    merged = {}
    for l, gs in segs.items():
        if not gs:
            continue
        m = linemerge(unary_union(gs))
        merged[l] = m
        parts = [m] if m.geom_type == 'LineString' else list(m.geoms)
        feats.append({"type": "Feature", "properties": {"kind": "line", "line": l},
                      "geometry": mapping(MultiLineString([p for p in parts]))})
    k = 111320 * math.cos(math.radians(38.89))
    for name, pts in sorted(stations.items()):
        lon = sum(p[0] for p in pts) / len(pts); lat = sum(p[1] for p in pts) / len(pts)
        pt = Point(lon, lat)
        near = [l for l in LINES if l in merged and merged[l].distance(pt) * k < 250]
        if not near:
            continue   # not on a Metrorail line (e.g. other rail)
        served = STATION_LINES.get(name)
        if served is None:
            print('  ! no line table entry for', name, '- using nearby lines', near)
            served = near
        if not (BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]):
            continue
        feats.append({"type": "Feature", "properties": {"kind": "station", "name": name, "lines": served},
                      "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(DATA / 'metro.geojson', 'w'))
    st = [f for f in feats if f['properties']['kind'] == 'station']
    print(len(st), 'stations;', {f['properties']['line']: len(f['geometry']['coordinates']) for f in feats if f['properties']['kind'] == 'line'})
    for f in st:
        print('  ', f['properties']['name'], f['properties']['lines'])

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else str(BASEMAP_BIN))
