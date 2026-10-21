#!/usr/bin/env bash
# Rebuild index.html from scratch. Steps marked (net) need internet access.
set -euo pipefail
cd "$(dirname "$0")"
P=pipeline

if [ ! -f data/raw/mcm_basemap_small.bin ] || [ "${REFETCH:-0}" = 1 ]; then
  python3 $P/fetch_basemap.py              # (net) OSM vector tiles for the map area, from a Protomaps build
fi
python3 $P/roads.py                        # z15 road geometry with names       -> data/roads.geojson
python3 $P/node_roads.py                   # split roads at at-grade crossings   -> data/noded_roads.geojson
python3 $P/build_graph.py                  # routing graph                       -> data/graph.pkl
python3 $P/route.py                        # certified course traced on streets  -> data/route.json
python3 $P/closures.py                     # closures snapped to streets         -> data/closures.geojson
python3 $P/slim.py                         # trimmed basemap (no buildings)      -> data/mcm_small.pmtiles
python3 $P/metro.py                        # Metrorail lines + stations          -> data/metro.geojson
python3 $P/resample.py                     # route samples every 40 m            -> data/samples.json
if [ "${REFETCH:-0}" = 1 ] || [ ! -f data/elev_raw.json ]; then
  python3 $P/fetch_elevation.py            # (net) terrain heights               -> data/elev_raw.json
fi
python3 $P/elevation.py                    # cleaned profile                     -> data/elevation.json
python3 $P/build_map.py                    # the web page                        -> index.html
