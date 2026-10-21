"""Snap each published road closure to the OSM street network -> closures.geojson.

Each closure is (time window, description, road pattern, FROM, TO, group).
FROM / TO = (cross-street pattern or None, hint lat, hint lon). The endpoint is the node where the road
meets the cross street nearest the hint; with None it is the road node nearest the hint.
The closed stretch is the shortest path between the two endpoints that stays on the named road.
Ramps/interchanges that can't be pinned to one road are drawn as point markers (kind="point").
"""
import json
import math
import pickle
import re
import sys

import networkx as nx

from config import DATA
from graph import RoadGraph, hav  # noqa: E402,F401

g = pickle.load(open(DATA / 'graph.pkl', 'rb'))
G = g.G


def rx(pat):
    return re.compile(r'(^|\s)' + re.escape(pat) + r'(\s|$)', re.I) if pat else None


def node_has(n, r):
    return any(r.search(G[n][m]['name']) for m in G[n])


def endpoint(road_r, spec, radius=700):
    cross, lat, lon = spec
    cr = rx(cross)
    best, bd = None, 1e18
    for i in g.node_tree.query_ball_point(g._xy(lat, lon), radius):
        n = int(g.node_ids[i])
        if not node_has(n, road_r):
            continue
        if cr is not None and not node_has(n, cr):
            continue
        d = hav((lon, lat), g.coord[n])
        if d < bd:
            best, bd = n, d
    if best is None and cr is not None:
        # cross street doesn't touch the road in the data: take the road node closest to the cross street
        cands = []
        for i in g.node_tree.query_ball_point(g._xy(lat, lon), radius):
            n = int(g.node_ids[i])
            if node_has(n, cr):
                cands.append(n)
        for i in g.node_tree.query_ball_point(g._xy(lat, lon), radius):
            n = int(g.node_ids[i])
            if not node_has(n, road_r):
                continue
            for c in cands:
                d = hav(g.coord[n], g.coord[c])
                if d < bd:
                    best, bd = n, d
        return best, ('near-cross', round(bd))
    return best, ('ix' if cr is not None else 'near', round(bd))


def road_path(road_r, a, b):
    def wf(x, y, d):
        return d['length'] * (1 if road_r.search(d['name']) else 25)
    return nx.shortest_path(G, a, b, weight=wf)


A = "Arlington 2026"
D = "DC (2025 list, unconfirmed for 2026)"
S = "Sun Oct 25"

# --------------------------------------------------------------------------- Arlington, 2026 list
C = [
    (f"{S} 3 AM-6 PM", "Fort Myer Dr, E. Langston Blvd to N. Meade St", "Fort Myer Drive", ("Langston", 38.8990, -77.0716), ("Meade", 38.8915, -77.0712), A),
    (f"{S} 3 AM-6 PM", "N. Lynn St, 19th St N to N. Meade St", "Lynn Street", ("19th Street North", 38.8963, -77.0728), ("Meade", 38.8925, -77.0725), A),
    (f"{S} 3 AM-6 PM", "N. Moore St, 19th St N to Wilson Blvd", "Moore Street", ("19th Street North", 38.89713, -77.0715), ("Wilson", 38.89512, -77.0715), A),
    (f"{S} 3 AM-6 PM", "Wilson Blvd, N. Oak St to SB Route 110", "Wilson Boulevard", ("Oak Street", 38.89481, -77.07384), (None, 38.8950, -77.0690), A),
    (f"{S} 3 AM-6 PM", "17th St N, Clarendon Blvd to N. Lynn St", "17th Street North", ("Clarendon", 38.89387, -77.07466), ("Lynn", 38.8940, -77.0710), A),
    (f"{S} 3 AM-6 PM", "N. Oak St, Clarendon Blvd to 17th St N", "Oak Street", ("Clarendon", 38.89451, -77.0738), ("17th Street North", 38.89402, -77.07371), A),
    (f"{S} 3 AM-6 PM", "N. Oak St (NB lanes), Wilson Blvd to 18th St N", "Oak Street", ("Wilson", 38.89481, -77.07384), ("18th Street North", 38.89568, -77.07396), A),
    (f"{S} 3 AM-6 PM", "N. Nash St, Wilson Blvd to 17th St N", "Nash Street", ("Wilson", 38.89488, -77.07314), ("17th Street North", 38.89405, -77.07276), A),
    (f"{S} 3 AM-6 PM", "N. Kent St, 1691 N. Kent St to Wilson Blvd", "Kent Street", ("Wilson", 38.89463, -77.06942), (None, 38.8962, -77.0694), A),
    (f"{S} 3 AM-6 PM", "Fairfax Dr, N. Pierce St to Fort Myer Dr", "Fairfax Drive", ("Pierce", 38.8920, -77.0780), ("Fort Myer", 38.8925, -77.0715), A),
    (f"{S} 3 AM-6 PM", "N. Meade St, Fairfax Dr to N. Marshall Dr", "Meade Street", (None, 38.8918, -77.0712), ("Marshall", 38.88765, -77.07173), A),
    (f"{S} 3 AM-6 PM", "N. Marshall Dr, N. Meade St to Route 110", "Marshall Drive", ("Meade", 38.88765, -77.07173), ("Richmond", 38.88808, -77.06631), A),
    (f"{S} 3 AM-6 PM", "S. Fern St, 12th St S to Rotary Rd", "Fern Street", ("12th Street South", 38.8628, -77.0563), ("Rotary", 38.8677, -77.0560), A),
    (f"{S} 3 AM-6 PM", "S. Eads St, 12th St S to Rotary Rd", "Eads Street", ("12th Street South", 38.8628, -77.0538), (None, 38.8674, -77.0541), A),
    (f"{S} 3 AM-6 PM", "Army Navy Dr, S. Hayes St to 12th St S", "Army Navy Drive", ("Hayes", 38.8660, -77.0590), ("12th Street South", 38.8628, -77.0517), A),
    (f"{S} 3 AM-6 PM", "Memorial Ave, Lincoln Circle to Arlington National Cemetery (pedestrian access only)", "Memorial Avenue", (None, 38.8845, -77.0590), (None, 38.8810, -77.0690), A),
    (f"{S} 3 AM-7 PM", "Marine Corps War Memorial Access Road", "US Marine Corps War Memorial Access Road", (None, 38.8879, -77.0677), (None, 38.8915, -77.0700), A),
    (f"{S} 6 AM-11 AM", "19th St N, N. Lynn St to Fort Myer Dr", "19th Street North", ("Lynn", 38.8963, -77.0728), ("Fort Myer", 38.8960, -77.0715), A),
    (f"{S} 6 AM-11 AM", "Fort Myer Dr, Key Bridge to WB Langston Blvd", "Fort Myer Drive", (None, 38.9005, -77.0707), ("Langston", 38.8990, -77.0716), A),
    (f"{S} 6 AM-11 AM", "Fort Myer Dr, 19th St N to Langston Blvd", "Fort Myer Drive", ("19th Street North", 38.8960, -77.0715), ("Langston", 38.8985, -77.0716), A),
    (f"{S} 6 AM-11 AM", "N. Moore St, 19th St N to Langston Blvd", "Moore Street", ("19th Street North", 38.89713, -77.0715), (None, 38.8990, -77.0715), A),
    (f"{S} 6 AM-5 PM", "Fort Myer Dr, Key Bridge to EB Langston Blvd", "Fort Myer Drive", (None, 38.9005, -77.0707), ("Langston", 38.8990, -77.0716), A),
    (f"{S} 6 AM-5 PM", "N. Nash St, WB to EB Langston Blvd; Key Blvd to Fort Myer Dr", "Nash Street", ("Key Boulevard", 38.89635, -77.07294), (None, 38.8990, -77.0726), A),
    (f"{S} 6 AM-5 PM", "Langston Blvd (EB lanes only), N. Lynn St to N. Kirkwood Rd", "Langston Boulevard", ("Lynn", 38.8982, -77.0708), ("Kirkwood", 38.89581, -77.09637), A),
    (f"{S} 6 AM-5 PM", "Spout Run Pkwy (WB lanes only), Langston Blvd to GW Pkwy", "Spout Run Parkway", (None, 38.8962, -77.0955), (None, 38.9020, -77.0790), A),
    (f"{S} 6 AM-5 PM", "N. Lorcom Ln, N. Edgewood St to Spout Run Pkwy", "Lorcom Lane", ("Edgewood", 38.89911, -77.09602), ("Spout Run", 38.89856, -77.09334), A),
    (f"{S} 6 AM-5 PM", "N. Lynn St, 19th St N to Key Bridge", "Lynn Street", ("19th Street North", 38.8963, -77.0728), (None, 38.9005, -77.0707), A),
    (f"{S} 6 AM-5 PM", "N. Rhodes St, Key Blvd to EB Langston Blvd", "Rhodes Street", ("Key Boulevard", 38.89517, -77.08188), ("Langston", 38.89637, -77.08207), A),
    (f"{S} 6 AM-5 PM", "N. Veitch St, 19th St N to EB Langston Blvd", "Veitch Street", ("19th Street North", 38.89547, -77.0864), ("Langston", 38.8959, -77.08647), A),
    (f"{S} 6 AM-5 PM", "Long Bridge Dr, Boundary Dr to 12th St S", "Long Bridge Drive", (None, 38.8700, -77.0465), ("12th Street South", 38.8630, -77.0505), A),
    (f"{S} 6 AM-5 PM", "6th St S, Long Bridge Dr to S. Ball St", "6th Street South", ("Long Bridge", 38.8655, -77.0480), ("Ball", 38.8655, -77.0490), A),
    (f"{S} 6 AM-5 PM", "S. Ball St, 6th St S to 10th St S", "Ball Street", ("6th Street South", 38.8655, -77.0490), ("10th Street South", 38.8640, -77.0495), A),
    (f"{S} 6 AM-5 PM", "10th St S, Long Bridge Dr to S. Ball St", "10th Street South", ("Long Bridge", 38.8640, -77.0490), ("Ball", 38.8640, -77.0495), A),
    (f"{S} 6 AM-5 PM", "12th St S, S. Eads St to Crystal Dr", "12th Street South", ("Eads", 38.8628, -77.0538), ("Crystal", 38.8624, -77.0488), A),
    (f"{S} 6 AM-5 PM", "Crystal Dr, 12th St S to 23rd St S", "Crystal Drive", ("12th Street South", 38.8624, -77.0488), ("23rd Street South", 38.8535, -77.0493), A),
    (f"{S} 6 AM-5 PM", "15th St S, S. Bell St to Crystal Dr", "15th Street South", ("Bell", 38.8600, -77.0505), ("Crystal", 38.8600, -77.0490), A),
    (f"{S} 6 AM-5 PM", "18th St S, S. Bell St to Crystal Dr", "18th Street South", ("Bell", 38.8575, -77.0505), ("Crystal", 38.8575, -77.0490), A),
    (f"{S} 6 AM-5 PM", "20th St S, S. Bell St to Crystal Dr", "20th Street South", ("Bell", 38.8555, -77.0505), ("Crystal", 38.8555, -77.0490), A),
    (f"{S} 5:30 AM-12 PM", "Parkway Drive, Rock Creek Pkwy to Lincoln Circle", "Parkway Drive", (None, 38.8915, -77.0530), (None, 38.8900, -77.0505), A),
    (f"{S} 5:30 AM-1 PM", "Lincoln Circle, 23rd St NW to 23rd St SW", "Lincoln Memorial Circle", (None, 38.8903, -77.0500), (None, 38.8880, -77.0490), A),
]

# point markers for ramps / interchanges (not attributable to one named road)
POINTS = [
    (f"{S} 3 AM-6 PM", "I-395 SB Exit 8B ramp to NB Route 110", 38.8655, -77.0565, A),
    (f"{S} 3 AM-6 PM", "I-395 NB slip ramp into NB HOT lanes; NB Exit 8B to Pentagon/Route 27; SB HOT lanes at Route 1", 38.8645, -77.0530, A),
    (f"{S} 3 AM-6 PM", "I-395 SB Exit 8A to Pentagon South Parking", 38.8665, -77.0585, A),
    (f"{S} 3 AM-6 PM", "EB Washington Blvd ramp to EB Route 27", 38.8700, -77.0610, A),
    (f"{S} 6 AM-5 PM", "I-395 N and S Exit 10A ramps to Boundary Channel Dr", 38.8700, -77.0490, A),
    (f"{S} 5:30 AM-11 AM", "S/B GW Memorial Parkway ramp to Key Bridge", 38.9002, -77.0698, A),
]
C += [
]

# --------------------------------------------------------------------------- DC, 2025 list (no 2026 list published yet)
DC = [
    ("Sun 3:45 AM-2 PM", "Jefferson Drive SW, 3rd St to 15th St", "Jefferson Drive", ("3rd Street", 38.8887, -77.0152), ("15th Street", 38.8886, -77.0330)),
    ("Sun 3:45 AM-2 PM", "7th Street, Constitution Ave NW to Independence Ave SW", "7th Street", ("Constitution", 38.8920, -77.0220), ("Independence", 38.8876, -77.0220)),
    ("Sun 3:45 AM-2 PM", "Madison Drive NW, 3rd St to 15th St", "Madison Drive", ("3rd Street", 38.8906, -77.0152), ("15th Street", 38.8901, -77.0330)),
    ("Sun 3:45 AM-2 PM", "4th Street, Constitution Ave NW to Independence Ave", "4th Street", ("Constitution", 38.8920, -77.0165), ("Independence", 38.8876, -77.0165)),
    ("Sun 5:30-10 AM", "Foxhall Road NW, MacArthur Blvd to Canal Rd", "Foxhall Road", ("MacArthur", 38.90686, -77.08114), ("Canal Road", 38.9060, -77.0790)),
    ("Sun 5:30-10 AM", "Clark Place NW, Q St to Canal Rd", "Clark Place", (None, 38.9088, -77.0880), ("Canal Road", 38.90673, -77.0868)),
    ("Sun 5:30-10 AM", "Reservoir Road NW, MacArthur Blvd to Canal Rd", "Reservoir Road", ("MacArthur", 38.91505, -77.09301), ("Canal Road", 38.91887, -77.10046)),
    ("Sun 5:30-10 AM", "Arizona Avenue NW, Carolina Pl to Canal Rd", "Arizona Avenue", ("Carolina", 38.92634, -77.10667), ("Canal Road", 38.92481, -77.10713)),
    ("Sun 5:30-10 AM", "Canal Road NW, M St to Chain Bridge", "Canal Road", ("M Street", 38.9050, -77.0700), (None, 38.9300, -77.1150)),
    ("Sun 5:30-10:30 AM", "Francis Scott Key Bridge (all lanes)", "Francis Scott Key Bridge", (None, 38.9006, -77.0707), (None, 38.9050, -77.0687)),
    ("Sun 5:30-10:30 AM", "M Street NW, Canal Rd to Wisconsin Ave", "M Street", ("Canal Road", 38.9050, -77.0700), ("Wisconsin", 38.9052, -77.0628)),
    ("Sun 5:30-10:30 AM", "35th Street NW, Prospect St to M St", "35th Street", ("Prospect", 38.9055, -77.0690), ("M Street", 38.9052, -77.0690)),
    ("Sun 5:30-10:30 AM", "34th Street NW, Prospect St to Cady's Alley", "34th Street", ("Prospect", 38.9055, -77.0680), (None, 38.9047, -77.0680)),
    ("Sun 5:30-10:30 AM", "Bank Alley, Prospect St to M St", "Bank Alley", (None, 38.9056, -77.0652), (None, 38.9051, -77.0652)),
    ("Sun 5:30-10:30 AM", "33rd Street NW, Prospect St to C&O Canal", "33rd Street", ("Prospect", 38.9055, -77.0670), (None, 38.9045, -77.0670)),
    ("Sun 5:30-10:30 AM", "Potomac Street NW, Prospect St to M St", "Potomac Street", ("Prospect", 38.9055, -77.0660), ("M Street", 38.9052, -77.0660)),
    ("Sun 5:30-10:30 AM", "Wisconsin Avenue NW, M St to K St", "Wisconsin Avenue", ("M Street", 38.9052, -77.0628), ("K Street", 38.9026, -77.0628)),
    ("Sun 5:30-10:30 AM", "Grace Street NW, Wisconsin Ave to 33rd St", "Grace Street", ("Wisconsin", 38.9040, -77.0628), ("33rd Street", 38.9040, -77.0660)),
    ("Sun 5:30-11 AM", "31st Street NW, Washington Harbour to South St", "31st Street", (None, 38.9020, -77.0610), ("South Street", 38.9033, -77.0612)),
    ("Sun 5:30-11 AM", "30th Street NW, Washington Harbour to M St", "30th Street", (None, 38.9025, -77.0598), ("M Street", 38.9052, -77.0598)),
    ("Sun 5:30-11 AM", "29th Street NW, K St to M St", "29th Street", ("K Street", 38.9028, -77.0583), ("M Street", 38.9052, -77.0583)),
    ("Sun 5:30-11 AM", "Whitehurst Freeway, M St to K St", "Whitehurst Freeway", (None, 38.9045, -77.0680), (None, 38.9028, -77.0565)),
    ("Sun 5:30-11 AM", "K Street NW, 34th St to 25th St", "K Street", (None, 38.9030, -77.0655), ("25th Street", 38.9027, -77.0535)),
    ("Sun 5:30-11 AM", "27th Street NW, K St to I St", "27th Street", ("K Street", 38.9025, -77.0560), ("I Street", 38.9010, -77.0560)),
    ("Sun 5:30-11 AM", "I Street NW, 27th St to Virginia Ave", "I Street", ("27th Street", 38.9010, -77.0560), ("Virginia", 38.9008, -77.0545)),
    ("Sun 5:30-11:30 AM", "Waterside Drive NW, Massachusetts Ave to Rock Creek Pkwy", "Waterside Drive", ("Massachusetts", 38.91703, -77.05731), (None, 38.9150, -77.0575)),
    ("Sun 5:30-11:45 AM", "Shoreham Drive NW (SB), Calvert St to Rock Creek Pkwy", "Shoreham Drive", ("Calvert", 38.9235, -77.0530), (None, 38.9214, -77.0515)),
    ("Sun 5:30-11:45 AM", "Beach Drive NW, Rock Creek Pkwy to Calvert St", "Beach Drive", (None, 38.9220, -77.0515), (None, 38.9245, -77.0520)),
    ("Sun 5:30-11:45 AM", "Virginia Avenue NW, New Hampshire Ave to Rock Creek Pkwy", "Virginia Avenue", ("New Hampshire", 38.8985, -77.0540), (None, 38.9008, -77.0572)),
    ("Sun 5:30 AM-12 PM", "F Street NW, New Hampshire Ave to Rock Creek Pkwy", "F Street", ("New Hampshire", 38.8968, -77.0545), (None, 38.8970, -77.0560)),
    ("Sun 5:30 AM-12 PM", "25th Street NW, F St to Rock Creek Pkwy", "25th Street", ("F Street", 38.8968, -77.0545), (None, 38.8950, -77.0550)),
    ("Sun 5:30 AM-12:30 PM", "Independence Avenue SW, Maine Ave to Ohio Dr", "Independence Avenue", ("Maine", 38.8873, -77.0372), ("Ohio Drive", 38.8870, -77.0480)),
    ("Sun 5:30 AM-12:45 PM", "Buckeye Drive SW, I-395 ramps to Ohio Dr", "Buckeye Drive", (None, 38.8788, -77.0294), (None, 38.8752, -77.0340)),
    ("Sun 5:30 AM-1 PM", "1st Street, Constitution Ave NW to Independence Ave SW", "1st Street", ("Constitution", 38.8921, -77.0125), ("Independence", 38.8876, -77.0125)),
    ("Sun 5:30 AM-1 PM", "Pennsylvania Avenue NW, 3rd St to 1st St", "Pennsylvania Avenue", ("3rd Street", 38.8915, -77.0152), (None, 38.8908, -77.0128)),
    ("Sun 5:30 AM-1 PM", "Maryland Avenue SW, 1st St to 3rd St", "Maryland Avenue", (None, 38.8890, -77.0128), ("3rd Street", 38.8882, -77.0152)),
    ("Sun 5:30 AM-1 PM", "West Basin Drive SW, Independence Ave to Ohio Dr", "West Basin Drive", ("Independence", 38.8870, -77.0452), (None, 38.8842, -77.0470)),
    ("Sun 5:30 AM-1 PM", "17th Street, WWII Memorial to Independence Ave SW", "17th Street", (None, 38.8895, -77.0395), ("Independence", 38.8880, -77.0395)),
    ("Sun 5:30 AM-1:15 PM", "Independence Avenue, 15th St to 23rd St SW", "Independence Avenue", ("15th Street", 38.8875, -77.0335), (None, 38.8870, -77.0490)),
    ("Sun 5:30 AM-1:15 PM", "Maine Avenue SW, East Basin Dr to Independence Ave", "Maine Avenue", (None, 38.8836, -77.0320), ("Independence", 38.8873, -77.0372)),
    ("Sun 5:30 AM-2 PM", "15th Street, Constitution Ave NW to Maine Ave SW", "15th Street", ("Constitution", 38.8922, -77.0330), ("Maine", 38.8846, -77.0336)),
    ("Sun 5:30 AM-2 PM", "Independence Avenue, 4th St to 15th St SW", "Independence Avenue", ("4th Street", 38.8876, -77.0165), ("15th Street", 38.8875, -77.0335)),
    ("Sun 5:30 AM-2 PM", "12th Street NW, Madison Dr to Constitution Ave", "12th Street", ("Madison", 38.8910, -77.0280), ("Constitution", 38.8921, -77.0280)),
    ("Sun 5:30 AM-2 PM", "14th Street NW/SW, Constitution Ave to I-395", "14th Street", ("Constitution", 38.8922, -77.0322), (None, 38.8810, -77.0330)),
]
C += [(w, d, r, f, t, D) for w, d, r, f, t in DC]

# Multi-carriageway roads: every carriageway of the named road inside the closed extent (lon/lat box)
SPANS = [
    (f"{S} 3 AM-6 PM", "Richmond Hwy (VA-110), I-66 to the 1200 block", "Richmond Highway", (-77.0700, 38.8690, -77.0500, 38.8930), A),
    (f"{S} 3 AM-6 PM", "SB Route 110, I-66 to Washington Blvd", "Richmond Highway", (-77.0700, 38.8795, -77.0500, 38.8930), A),
    ("Sat Oct 24 4 PM - Sun Oct 25 5 PM", "SB Route 110, Washington Blvd to Route 1", "Richmond Highway", (-77.0620, 38.8660, -77.0500, 38.8795), A),
    (f"{S} 3 AM-6 PM", "NB Route 110, Route 1 to I-66/Wilson Blvd", "Richmond Highway", (-77.0700, 38.8660, -77.0500, 38.8930), A),
    (f"{S} 6 AM-5 PM", "SB Richmond Hwy (US-1), I-395 to the 1200 block", "Richmond Highway", (-77.0530, 38.8620, -77.0500, 38.8662), A),
    (f"{S} 3 AM-3 PM", "N/B HOT lanes (395 Express Lanes), Seminary Rd to 14th St SW (from the edge of the street-level map)", "395 Express", (-77.1200, 38.8300, -77.0300, 38.8810), A),
    (f"{S} 3 AM-6 PM", "Washington Blvd (Route 27), Route 27/NB I-395 split to GW Pkwy/Boundary Channel", "Washington Boulevard", (-77.0665, 38.8655, -77.0550, 38.8825), A),
    (f"{S} 3 AM-5 PM", "Route 27 (Washington Blvd) EB and WB, I-395 to US-50", "Washington Boulevard", (-77.0665, 38.8655, -77.0550, 38.8825), A),
    (f"{S} 5:30 AM-11 AM", "N/B GW Memorial Parkway, I-395 to Spout Run Pkwy", "George Washington Memorial Parkway", (-77.0800, 38.8690, -77.0400, 38.9035), A),
    ("Sun 5:30-11:45 AM", "Rock Creek and Potomac Pkwy NW (both directions), Ohio Dr to Beach/Shoreham Dr", "Rock Creek", (-77.0600, 38.8915, -77.0450, 38.9222), D),
    ("Sun 5:30 AM-1 PM", "Ohio Drive SW, East Basin Dr to 23rd St NW", "Ohio Drive", (-77.0520, 38.8790, -77.0320, 38.8920), D),
    ("Sun 5:30 AM-2 PM", "12th Street SW, Independence Ave to Jefferson Dr", "12th Street", (-77.0290, 38.8873, -77.0272, 38.8889), D),
]
POINTS += [
    ("Sun 5:30 AM-12:45 PM", "East Basin Drive SW, Maine Ave to Ohio Dr (not named in the map data; location approximate)", 38.8815, -77.0320, D),
]


def merge(segs):
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    m = linemerge(MultiLineString(segs))
    parts = [m] if m.geom_type == 'LineString' else list(m.geoms)
    return [[list(c) for c in p.coords] for p in parts]


def build():
    feats, problems = [], []
    for win, desc, road, frm, to, grp in C:
        rr = rx(road)
        a, ma = endpoint(rr, frm)
        b, mb = endpoint(rr, to)
        if a is None or b is None or a == b:
            problems.append((desc, 'endpoint', ma, mb))
            continue
        p = road_path(rr, a, b)
        on = sum(G[x][y]['length'] for x, y in zip(p, p[1:]) if rr.search(G[x][y]['name']))
        L = g.length(p)
        straight = hav(g.coord[a], g.coord[b])
        flag = []
        if L > 0 and on / L < 0.85:
            flag.append(f'only {on / L:.0%} on {road}')
        if straight > 30 and L / straight > 2.2:
            flag.append(f'winding x{L / straight:.1f}')
        if ma[1] > 250 or mb[1] > 250:
            flag.append(f'endpoint far from hint {ma} {mb}')
        if flag:
            problems.append((desc, '; '.join(flag)))
        feats.append({"type": "Feature",
                      "properties": {"window": win, "desc": desc, "group": grp, "kind": "line",
                                     "length_m": round(L)},
                      "geometry": {"type": "LineString", "coordinates": [list(g.coord[n]) for n in p]}})
    for win, desc, road, bbox in [(w, d, r, b) for w, d, r, b, _ in SPANS]:
        pass
    for win, desc, road, (w_, s_, e_, n_), grp in SPANS:
        rr = rx(road)
        segs = []
        for x, y, d in G.edges(data=True):
            if not rr.search(d['name']):
                continue
            (x1, y1), (x2, y2) = g.coord[x], g.coord[y]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if w_ <= mx <= e_ and s_ <= my <= n_:
                segs.append([[x1, y1], [x2, y2]])
        if not segs:
            problems.append((desc, 'empty span'))
            continue
        feats.append({"type": "Feature", "properties": {"window": win, "desc": desc, "group": grp, "kind": "line"},
                      "geometry": {"type": "MultiLineString", "coordinates": merge(segs)}})
    for win, desc, lat, lon, grp in POINTS:
        feats.append({"type": "Feature", "properties": {"window": win, "desc": desc, "group": grp, "kind": "point"},
                      "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(DATA / 'closures.geojson', 'w'))
    print(len(feats), 'features;', len(problems), 'flagged')
    for p in problems:
        print('  !', p)


if __name__ == '__main__':
    build()
