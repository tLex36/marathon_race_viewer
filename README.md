# Marathon Race Viewer: Marine Corps Marathon 2026

An interactive, mobile-friendly map of the **2026 Marine Corps Marathon** (Sunday, Oct 25, 2026) for runners and
spectators, plus a race-morning logistics guide.

**Live page:** https://tlex36.github.io/marathon_race_viewer/
(add `#logistics` to open the Logistics tab directly)

The whole site is a single self-contained `index.html` (about 10.5 MB). The basemap, map libraries and data are
embedded, so it needs no tile server or API key, and it also works offline if you download the file.

## What's on the page

**Map tab**
- **Race route**: the USATF-certified course (cert. DC25002LMJ) traced along OpenStreetMap streets, with green and
  red checkered flags for start and finish, approximate mile markers, and the three gauntlet cut-off points
  (orange dots).
- **Road closures**: snapped to the named streets, with extent and hours on hover or tap. Arlington uses the 2026
  closure list. DC uses the 2025 list, because no 2026 DC list had been published when this was built.
- **Metrorail**: lines in WMATA colours (shared track drawn as side-by-side bands) and a rail-car icon at each
  station, showing the lines that stop there.
- **Elevation chart**: hover or drag along it and a runner icon moves along the course; hover or tap the course
  to highlight that stretch on the chart.
- **Layers**: tap a legend row to show or hide each layer.

**Logistics tab**: getting to the start by Metro, what to wear, and what to expect on course.

## Data sources and accuracy

| Layer | Source | Notes |
|---|---|---|
| Basemap, streets, Metro lines and stations | OpenStreetMap via a [Protomaps](https://maps.protomaps.com/builds/) daily build (2026-10-20) | Trimmed to the course and closures plus 1.5 mi; building outlines removed to keep the file small |
| Course | [MCM certified course map](https://www.marinemarathon.com/event/marine-corps-marathon/map/) | Traced on street centrelines: 26.67 mi traced vs 26.22 mi certified (the certified measurement takes the shortest legal line) |
| Road closures | Arlington: [ANC notice](https://www.arlingtoncemetery.mil/Media/News/Post/15152/marine-corps-marathon-road-closures-sunday-oct-25-), [ARLnow](https://www.arlnow.com/2026/10/20/marine-corps-marathon-returns-this-weekend-bringing-arlington-road-closures/). DC: [MCM 2025 list](https://www.marinemarathon.com/mcm-road-closures/) | Times are approximate. Ramps and interchanges are shown as points |
| Elevation | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (USGS 3DEP-derived), sampled every 40 m | Bridge decks are interpolated between their ends, so the 14th St Bridge reads flatter than reality |
| Race times, Metro hours | [MCM race-day page](https://www.marinemarathon.com/event/marine-corps-marathon/race-day/), [MCM travel page](https://www.marinemarathon.com/event/marine-corps-marathon/travel-hotel/) | |

This is an unofficial page. Confirm closures, times and Metro service with official sources before race day.

## How it's built

A Python pipeline (`pipeline/`) produces `index.html` with [folium](https://python-visualization.github.io/folium/)
(Leaflet). The basemap is drawn in the browser by
[protomaps-leaflet](https://github.com/protomaps/protomaps-leaflet) from an embedded PMTiles archive.

| Step | Script | Output (`data/`) |
|---|---|---|
| 1 | `fetch_basemap.py`: download OSM vector tiles for the map area (HTTP range requests, stdlib only) | `raw/mcm_basemap_small.bin` |
| 2 | `roads.py`, `node_roads.py`: decode named road geometry and split it at at-grade crossings (bridges and tunnels kept separate) | `roads.geojson`, `noded_roads.geojson` |
| 3 | `build_graph.py`: routing graph (merges tile seams, joins dangling ends) | `graph.pkl` |
| 4 | `route.py`: trace the certified course leg by leg, preferring the street names on the certified map | `route.json` |
| 5 | `closures.py`: snap each closure to its street between its cross streets | `closures.geojson` |
| 6 | `slim.py`: trim the basemap and drop building outlines | `mcm_small.pmtiles` |
| 7 | `metro.py`: Metrorail lines and stations | `metro.geojson` |
| 8 | `resample.py`, `fetch_elevation.py`, `elevation.py`: elevation profile | `elevation.json` |
| 9 | `build_map.py`: assemble the page, inlining all JS, CSS and data | `../index.html` |

The small data files the page needs are committed in `data/`, so you can rebuild the page without downloading
anything.

## Rebuild

```bash
pip install -r requirements.txt
npm install                    # leaflet, pmtiles, protomaps-leaflet (inlined into the page)
python3 pipeline/build_map.py  # rebuild index.html from the committed data/
```

To regenerate everything from scratch (needs internet; downloads about 16 MB of map tiles):

```bash
REFETCH=1 ./run_all.sh
```

`tools/plot_area.py` draws a labelled street plot of any area, which is useful for checking route and closure
alignment.

## Repository layout

```
index.html          the site (GitHub Pages serves this)
pipeline/           build scripts (see table above); config.py holds the paths
data/               committed inputs and outputs used to build the page
data/raw/           large downloads (git-ignored)
tools/plot_area.py  debugging plot of streets, route and closures
run_all.sh          full rebuild
```

## Licences and attribution

- Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), available under the ODbL;
  vector tiles by [Protomaps](https://protomaps.com).
- Elevation: USGS 3DEP (public domain) via AWS Terrain Tiles.
- Libraries inlined in `index.html`: Leaflet (BSD-2-Clause), pmtiles (BSD-3-Clause), protomaps-leaflet (BSD-3-Clause).
- Course, closure and schedule details come from the official sources linked above.
