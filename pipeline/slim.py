"""Make a small basemap: keep tiles (zoom >= MINZ) that touch BOX, and drop the 'buildings' layer.
Usage: python3 pipeline/slim.py [in.bin|in.pmtiles] [out.pmtiles]"""
import gzip, json, math, struct, sys
import mapbox_vector_tile as mvt
from config import DATA, BASEMAP_BIN
from mvtlayers import split_layers, join_layers
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid, TileType, Compression

BOX = json.load(open(DATA / 'newbox.json'))
MINZ = 11
DROP = {'buildings'}

def t2lon(x, z): return x / (1 << z) * 360 - 180
def t2lat(y, z): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << z)))))

def tiles_from(path):
    if path.endswith('.bin'):
        d = open(path, 'rb').read()
        n = struct.unpack_from('<I', d, 5)[0]; meta = json.loads(d[9:9 + n]); base = 9 + n
        md = bytes.fromhex(meta['metadata'])
        md = json.loads(gzip.decompress(md) if meta['header']['internal_compression'] == 2 else md)
        for z, x, y, i in meta['tiles']:
            off, ln = meta['spans'][i]
            yield (z, x, y), d[base + off:base + off + ln]
        tiles_from.md = md
    else:
        from pmtiles.reader import Reader, MmapSource, all_tiles
        r = Reader(MmapSource(open(path, 'rb')))
        tiles_from.md = r.metadata()
        yield from all_tiles(r.get_bytes)

def main(src, dst):
    out, maxz = [], 0
    for (z, x, y), data in tiles_from(src):
        if z < MINZ:
            continue
        if t2lon(x + 1, z) < BOX[0] or t2lon(x, z) > BOX[2] or t2lat(y, z) < BOX[1] or t2lat(y + 1, z) > BOX[3]:
            continue
        L = []
        for name, msg in split_layers(gzip.decompress(data)):
            if name in DROP:
                continue
            if name == 'pois' and z >= 14:
                # keep only POIs Protomaps shows by zoom 15 (drops ~80k shop/amenity points seen only at z16+)
                lay = mvt.decode(join_layers([(name, msg)]))['pois']
                keep = [f for f in lay['features'] if (f['properties'].get('min_zoom') or 0) <= 15]
                if keep:
                    L += split_layers(mvt.encode([{'name': 'pois', 'features': keep}],
                                                 default_options={'extents': lay['extent']}))
                continue
            L.append((name, msg))
        out.append((zxy_to_tileid(z, x, y), gzip.compress(join_layers(L), 9)))
        maxz = max(maxz, z)
    out.sort()
    with open(dst, 'wb') as f:
        w = Writer(f)
        for tid, b in out:
            w.write_tile(tid, b)
        w.finalize({"tile_type": TileType.MVT, "tile_compression": Compression.GZIP, "min_zoom": MINZ, "max_zoom": maxz,
                    "min_lon_e7": int(BOX[0] * 1e7), "min_lat_e7": int(BOX[1] * 1e7),
                    "max_lon_e7": int(BOX[2] * 1e7), "max_lat_e7": int(BOX[3] * 1e7),
                    "center_zoom": 13, "center_lon_e7": int(-77.06e7), "center_lat_e7": int(38.885e7)}, tiles_from.md)
    import os
    print(f"{len(out)} tiles, {os.path.getsize(dst) / 1e6:.2f} MB -> {dst}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else str(BASEMAP_BIN),
         sys.argv[2] if len(sys.argv) > 2 else str(DATA / 'mcm_small.pmtiles'))
