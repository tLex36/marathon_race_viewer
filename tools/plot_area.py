import json, sys, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape, box
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'pipeline'))
from config import DATA
fc = json.load(open(DATA / 'noded_roads.geojson'))
def plot(bbox, out, label_kinds=('highway','major_road','minor_road','other'), overlay=None, title=''):
    w,s,e,n = bbox; B = box(*bbox)
    fig, ax = plt.subplots(figsize=(13,13*(n-s)/((e-w)*0.778)))
    seen = {}
    for f in fc['features']:
        g = shape(f['geometry'])
        if not g.intersects(B): continue
        p = f['properties']; k = p.get('kind')
        if k == 'path': ax.plot(*g.xy, color='#ddd', lw=0.4); continue
        col = {'highway':'#e07','major_road':'#e80','minor_road':'#888','other':'#bbb'}.get(k,'#ccc')
        ax.plot(*g.xy, color=col, lw=1.6 if k in ('highway','major_road') else 0.8)
        nm = p.get('name')
        if nm and k in label_kinds:
            c = g.interpolate(0.5, normalized=True)
            key = (nm, round(c.x,3), round(c.y,3))
            if key not in seen:
                seen[key]=1; ax.text(c.x, c.y, nm.replace('Northwest','NW').replace('Southwest','SW').replace('South ','S ').replace('North ','N '), fontsize=6, color='k')
    if overlay:
        for pts, col in overlay:
            ax.plot([p[1] for p in pts], [p[0] for p in pts], color=col, lw=3, alpha=0.6)
    ax.set_xlim(w,e); ax.set_ylim(s,n); ax.set_aspect(1/0.778); ax.grid(True, lw=0.3)
    ax.set_title(title); fig.savefig(out, dpi=110, bbox_inches='tight'); plt.close(fig)
if __name__ == '__main__':
    bbox = tuple(map(float, sys.argv[1:5])); plot(bbox, sys.argv[5])
