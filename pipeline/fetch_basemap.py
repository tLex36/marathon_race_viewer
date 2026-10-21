#!/usr/bin/env python3
"""Download the data for the Marine Corps Marathon map (standard library only, no installs).

Fetches:
  An OpenStreetMap vector-tile extract from the Protomaps daily build (ODbL data; Protomaps
  publishes these builds specifically so people can extract regions from them), zooms 10-15,
  covering only the race course and road closures plus 1.5 miles. HTTP range requests only.

Usage:   python3 pipeline/fetch_basemap.py       (writes data/raw/mcm_basemap_small.bin)
"""
import concurrent.futures as cf
import gzip
import io
import json
import math
import os
import struct
import sys
import time
import urllib.request

BUILD = "https://build.protomaps.com/20261020.pmtiles"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
# Course + all closures, plus 1.5 miles beyond their outermost points (lon/lat box)
BOX = (-77.1397, 38.8094, -76.9842, 38.9521)
ZOOMS = range(10, 16)               # city view down to street level, whole box
EXTRA_FILES = {}
UA = {"User-Agent": "mcm-map-builder/1.0 (personal, one-off regional extract)"}


# ---------------------------------------------------------------- PMTiles v3 helpers
def get_bytes(offset, length, url=BUILD, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={offset}-{offset + length - 1}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) != length:
                raise IOError(f"short read {len(data)} != {length}")
            return data
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def zxy_to_tileid(z, x, y):
    acc = ((1 << (z * 2)) - 1) // 3
    a = z - 1
    while a >= 0:
        s = 1 << a
        rx, ry = s & x, s & y
        acc += ((3 * rx) ^ ry) << a
        if ry == 0:
            if rx != 0:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        a -= 1
    return acc


def read_varint(b):
    shift = result = 0
    while True:
        byte = b.read(1)[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
        shift += 7


def parse_directory(buf):
    b = io.BytesIO(gzip.decompress(buf))
    n = read_varint(b)
    ids, last = [], 0
    for _ in range(n):
        last += read_varint(b)
        ids.append(last)
    runs = [read_varint(b) for _ in range(n)]
    lens = [read_varint(b) for _ in range(n)]
    offs = []
    for i in range(n):
        v = read_varint(b)
        offs.append(offs[i - 1] + lens[i - 1] if (i > 0 and v == 0) else v - 1)
    return list(zip(ids, runs, lens, offs))


def find_entry(entries, tid):
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        k = (lo + hi) >> 1
        c = tid - entries[k][0]
        if c > 0:
            lo = k + 1
        elif c < 0:
            hi = k - 1
        else:
            return entries[k]
    if hi >= 0:
        e = entries[hi]
        if e[1] == 0 or tid - e[0] < e[1]:
            return e
    return None


def lonlat_to_tile(lon, lat, z):
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tiles_in_bbox(bbox, zooms):
    w, s, e, n = bbox
    for z in zooms:
        x0, y0 = lonlat_to_tile(w, n, z)
        x1, y1 = lonlat_to_tile(e, s, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield z, x, y


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    wide = BOX
    wanted = sorted(set(tiles_in_bbox(BOX, ZOOMS)))
    print(f"Source: {BUILD}\nTiles requested: {len(wanted)}")

    raw = get_bytes(0, 16384)
    h = raw[:127]
    if h[:7] != b"PMTiles" or h[7] != 3:
        sys.exit("Not a PMTiles v3 archive")
    u64 = lambda p: struct.unpack_from("<Q", h, p)[0]  # noqa: E731
    hdr = dict(root_offset=u64(8), root_length=u64(16), metadata_offset=u64(24), metadata_length=u64(32),
               leaf_offset=u64(40), leaf_length=u64(48), data_offset=u64(56),
               internal_compression=h[97], tile_compression=h[98], tile_type=h[99])
    root = parse_directory(raw[hdr["root_offset"]:hdr["root_offset"] + hdr["root_length"]]
                           if hdr["root_offset"] + hdr["root_length"] <= len(raw)
                           else get_bytes(hdr["root_offset"], hdr["root_length"]))
    metadata = get_bytes(hdr["metadata_offset"], hdr["metadata_length"])

    leaf_cache = {}

    def resolve(tid):
        entries = root
        for _ in range(4):
            e = find_entry(entries, tid)
            if e is None:
                return None
            if e[1] > 0:
                return e
            key = (e[3], e[2])
            if key not in leaf_cache:
                leaf_cache[key] = parse_directory(get_bytes(hdr["leaf_offset"] + e[3], e[2]))
            entries = leaf_cache[key]
        return None

    index, blobs = [], {}
    for z, x, y in wanted:
        e = resolve(zxy_to_tileid(z, x, y))
        if e is None:
            continue
        key = (e[3], e[2])
        blobs.setdefault(key, None)
        index.append((z, x, y, key))
    total = sum(k[1] for k in blobs)
    print(f"Tiles present: {len(index)}  unique blobs: {len(blobs)}  "
          f"leaf dirs read: {len(leaf_cache)}  download size: {total / 1e6:.1f} MB")

    # merge nearby byte ranges into fewer requests
    keys = sorted(blobs)
    groups, cur = [], [keys[0]]
    for k in keys[1:]:
        start, end = cur[0][0], cur[-1][0] + cur[-1][1]
        if k[0] - end < 65536 and (k[0] + k[1] - start) < 8_000_000:
            cur.append(k)
        else:
            groups.append(cur)
            cur = [k]
    groups.append(cur)

    def fetch_group(g):
        start = g[0][0]
        buf = get_bytes(hdr["data_offset"] + start, g[-1][0] + g[-1][1] - start)
        return {k: buf[k[0] - start:k[0] - start + k[1]] for k in g}

    done = 0
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(fetch_group, groups):
            blobs.update(res)
            done += 1
            print(f"\r  fetched {done}/{len(groups)} ranges", end="", flush=True)
    print()

    # container: b"MCMT1" + u32 json length + json + data
    order = {k: i for i, k in enumerate(keys)}
    pos, spans = 0, []
    for k in keys:
        spans.append([pos, k[1]])
        pos += k[1]
    meta = dict(source=BUILD, header=hdr, metadata=metadata.hex(), wide_bbox=wide, corridor_bbox=BOX,
                tiles=[[z, x, y, order[k]] for z, x, y, k in index], spans=spans)
    mj = json.dumps(meta).encode()
    out = os.path.join(OUT_DIR, "mcm_basemap_small.bin")
    with open(out, "wb") as f:
        f.write(b"MCMT1" + struct.pack("<I", len(mj)) + mj)
        for k in keys:
            f.write(blobs[k])
    print(f"Wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")

    for name, url in EXTRA_FILES.items():
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(os.path.join(OUT_DIR, name), "wb") as f:
                f.write(r.read())
            print(f"Wrote {name}")
        except Exception as e:  # noqa: BLE001
            print(f"Could not download {name}: {e}")
    print("Done.")


if __name__ == "__main__":
    main()
