"""Routing graph built from the decoded OSM roads (roads.geojson)."""
import json, math
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

R = 6371000.0
KIND_W = {"highway": 1.0, "major_road": 1.0, "minor_road": 1.0, "other": 1.6, "path": 4.0}


def hav(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class RoadGraph:
    def __init__(self, path="roads.geojson", snap_m=1.5, join_m=10.0):
        fc = json.load(open(path))
        self.feats = fc["features"]
        pts = []
        for f in self.feats:
            for c in f["geometry"]["coordinates"]:
                pts.append(c)
        pts = np.array(pts)
        # cluster vertices within snap_m metres (merges tile-boundary splits and shared OSM nodes)
        k = 111320.0
        xy = np.c_[pts[:, 0] * k * math.cos(math.radians(38.89)), pts[:, 1] * k]
        tree = cKDTree(xy)
        parent = np.arange(len(pts))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, j in tree.query_pairs(snap_m):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj
        roots = np.array([find(i) for i in range(len(pts))])
        self.coord = {}
        for i, r in enumerate(roots):
            self.coord.setdefault(int(r), tuple(pts[r]))
        G = nx.Graph()
        idx = 0
        for fi, f in enumerate(self.feats):
            cs = f["geometry"]["coordinates"]
            p = f["properties"]
            w = KIND_W.get(p.get("kind"), 2.0)
            ids = [int(roots[idx + t]) for t in range(len(cs))]
            idx += len(cs)
            for a, b in zip(ids, ids[1:]):
                if a == b:
                    continue
                L = hav(self.coord[a], self.coord[b])
                if G.has_edge(a, b) and G[a][b]["w"] <= L * w:
                    continue
                G.add_edge(a, b, length=L, w=L * w, name=p.get("name") or "", kind=p.get("kind"),
                           detail=p.get("kind_detail"), ref=p.get("ref") or "", fi=fi)
        # Join dangling road ends (degree 1) to the nearest other node within `join_m`:
        # z15 simplification often leaves bridge/ramp ends a few metres short of the road they meet.
        nodes0 = list(G.nodes)
        nxy0 = np.array([self.coord[n] for n in nodes0])
        t0 = cKDTree(np.c_[nxy0[:, 0] * k * math.cos(math.radians(38.89)), nxy0[:, 1] * k])
        added = 0
        for n in nodes0:
            if G.degree(n) != 1:
                continue
            (m, d), = G[n].items()
            if d["kind"] == "path":
                continue
            c = self.coord[n]
            dist, idx = t0.query((c[0] * k * math.cos(math.radians(38.89)), c[1] * k), k=6,
                                 distance_upper_bound=join_m)
            for dd, ii in zip(dist, idx):
                if not np.isfinite(dd):
                    break
                o = nodes0[ii]
                if o == n or o == m or G.has_edge(n, o):
                    continue
                L = hav(self.coord[n], self.coord[o])
                G.add_edge(n, o, length=L, w=L, name=d["name"], kind=d["kind"], detail=d["detail"],
                           ref=d["ref"], fi=d["fi"], joined=True)
                added += 1
                break
        self.joined = added
        self.G = G
        nodes = list(G.nodes)
        self.node_ids = np.array(nodes)
        nxy = np.array([self.coord[n] for n in nodes])
        self.node_tree = cKDTree(np.c_[nxy[:, 0] * k * math.cos(math.radians(38.89)), nxy[:, 1] * k])
        self.k = k

    def _xy(self, lat, lon):
        return (lon * self.k * math.cos(math.radians(38.89)), lat * self.k)

    def nearest(self, lat, lon, name=None, radius=400):
        """Nearest graph node to a point, optionally restricted to nodes on a road whose name contains `name`."""
        cand = self.node_tree.query_ball_point(self._xy(lat, lon), radius)
        best, bd = None, 1e18
        for c in cand:
            n = int(self.node_ids[c])
            if name and not any(name.lower() in self.G[n][m]["name"].lower() for m in self.G[n]):
                continue
            d = hav((lon, lat), self.coord[n])
            if d < bd:
                best, bd = n, d
        return best, bd

    def intersection(self, a, b, near, radius=600):
        """Node where roads named a and b meet, closest to `near` (lat, lon)."""
        cand = self.node_tree.query_ball_point(self._xy(*near), radius)
        best, bd = None, 1e18
        for c in cand:
            n = int(self.node_ids[c])
            names = [self.G[n][m]["name"].lower() for m in self.G[n]]
            if any(a.lower() in s for s in names) and any(b.lower() in s for s in names):
                d = hav((near[1], near[0]), self.coord[n])
                if d < bd:
                    best, bd = n, d
        return best, bd

    def path(self, u, v, prefer=(), avoid=(), penalty=6.0):
        prefer = [p.lower() for p in prefer]
        avoid = [p.lower() for p in avoid]

        def wf(x, y, d):
            w = d["w"]
            nm = d["name"].lower()
            if prefer and not any(p in nm for p in prefer):
                w *= penalty
            if avoid and any(p in nm for p in avoid):
                w *= 50
            return w
        return nx.shortest_path(self.G, u, v, weight=wf)

    def coords(self, nodes):
        return [(self.coord[n][1], self.coord[n][0]) for n in nodes]  # (lat, lon)

    def length(self, nodes):
        return sum(self.G[a][b]["length"] for a, b in zip(nodes, nodes[1:]))
