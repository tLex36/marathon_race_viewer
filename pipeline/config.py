"""Shared paths for the pipeline (everything is relative to the repository root)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'                 # small, committed inputs/outputs used to build the page
RAW = DATA / 'raw'                   # large downloads (git-ignored)
NODE_MODULES = ROOT / 'node_modules' # leaflet, pmtiles, protomaps-leaflet (npm install)
BASEMAP_BIN = RAW / 'mcm_basemap_small.bin'
SITE = ROOT / 'index.html'           # GitHub Pages entry point
