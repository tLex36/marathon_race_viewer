"""Trace the certified MCM course (USATF DC25002LMJ, effective 10-4-2025 through 12-31-2035) along OSM streets.

Each leg routes from the previous point to a target point over the OSM road graph, preferring the
street names the certified map gives for that leg. Output: route.json [[lat, lon], ...].
"""
import json
import pickle
import sys

from config import DATA
from graph import RoadGraph  # noqa: E402,F401

g = pickle.load(open(DATA / 'graph.pkl', 'rb'))

# Known gaps left by z15 simplification where a ramp meets a bridge end (checked on the plotted data).
MANUAL_JOINS = [
    ((38.900579, -77.070605), (38.900569, -77.070712), "GW Pkwy NB on-ramp meets south end of Key Bridge", "Francis Scott Key Bridge"),
    ((38.86695, -77.05289), (38.86689, -77.05409), "Pork Chop Lot south aisle back to S Eads St (straight aisle along the lot edge)", "Pentagon Access Road"),
]
for (a_lat, a_lon), (b_lat, b_lon), why, nm in MANUAL_JOINS:
    a, _ = g.nearest(a_lat, a_lon, radius=3)
    b, _ = g.nearest(b_lat, b_lon, radius=3)
    L = ((g.coord[a][0] - g.coord[b][0]) ** 2 + (g.coord[a][1] - g.coord[b][1]) ** 2) ** 0.5 * 111320 * 0.85
    g.G.add_edge(a, b, length=L, w=L, name=nm, kind='major_road', detail='link', ref='', fi=-1)


def IX(a, b, lat, lon):
    n, d = g.intersection(a, b, (lat, lon))
    assert n is not None, f"no intersection {a} x {b}"
    return n


def NEAR(lat, lon, name=None):
    n, d = g.nearest(lat, lon, name)
    assert n is not None, f"nothing near {lat},{lon} {name}"
    return n


START = NEAR(38.882706, -77.062642, 'Richmond')          # certified start, NB lanes of VA-110
LEGS = [
    # (label, target node, preferred street names)
    ("Rt 110 north to Wilson Blvd", IX('Wilson', 'Lynn', 38.8953, -77.0712), ['Richmond', 'Wilson']),
    ("N Lynn St north (mile 1)", IX('Lynn', 'Langston', 38.8982, -77.0708), ['Lynn']),
    ("Langston Blvd west (mile 2)", IX('Langston', 'Spout Run', 38.8962, -77.0955), ['Langston']),
    # runners use the GW Pkwy carriageway that the Key Bridge on-ramp joins (certified: "GWMP Westbound")
    ("Spout Run Pkwy + GW Pkwy westbound lanes (miles 3-4)", NEAR(38.900761, -77.071165, 'George Washington'), ['Spout Run', 'George Washington']),
    ("On-ramp up to Key Bridge", IX('Key Bridge', 'M Street', 38.9051, -77.0687), ['George Washington', 'Key Bridge', 'Lynn', 'Fort Myer']),
    ("M Street NW east", IX('M Street', 'Wisconsin', 38.9052, -77.0628), ['M Street']),
    ("Wisconsin Ave south", IX('Wisconsin', 'K Street', 38.9026, -77.0628), ['Wisconsin']),
    ("K Street NW east (mile 5)", IX('K Street', '27th', 38.9025, -77.0560), ['K Street']),
    ("27th St south", IX('27th', 'Virginia', 38.9007, -77.0559), ['27th']),
    ("Virginia Ave to Parkway", NEAR(38.9008, -77.0572, 'Rock Creek'), ['Virginia']),
    ("Rock Creek Pkwy north to turnaround (miles 6-7)", IX('Rock Creek', 'Shoreham', 38.9214, -77.0512), ['Rock Creek']),
    ("Parkway south past Kennedy Center (miles 8-10)", NEAR(38.8930, -77.0560, 'Rock Creek'), ['Rock Creek']),
    ("Ohio Dr / Independence to West Basin Dr (mile 11)", IX('Independence', 'West Basin', 38.8870, -77.0452), ['Rock Creek', 'Ohio Drive', 'Independence']),
    ("West Basin Dr / Ohio Dr to Hains Point (miles 12-13)", NEAR(38.85833, -77.02268, 'Ohio Drive'), ['West Basin', 'Ohio Drive']),
    ("Ohio Dr east side north (miles 14-15)", NEAR(38.8800, -77.0300, 'Ohio Drive'), ['Ohio Drive']),
    ("to Maine Ave / Raoul Wallenberg Pl", IX('15th Street', 'Maine', 38.8846, -77.0336), ['Ohio Drive', 'West Basin', 'Maine', '15th Street']),
    ("Raoul Wallenberg Pl north", IX('15th Street', 'Independence', 38.8875, -77.0335), ['15th Street']),
    ("Independence Ave west to turn (mile 16)", NEAR(38.8870, -77.0412, 'Independence'), ['Independence']),
    ("Independence Ave back east", IX('15th Street', 'Independence', 38.8875, -77.0335), ['Independence']),
    ("15th St north to Madison Dr", IX('15th Street', 'Madison', 38.8902, -77.0330), ['15th Street']),
    ("Madison Dr east (mile 17)", IX('Madison', '3rd Street', 38.8912, -77.0153), ['Madison']),
    ("3rd St / Pennsylvania Ave to Peace Circle", NEAR(38.8907, -77.0124, 'Peace Monument'), ['3rd Street', 'Pennsylvania', 'Peace Monument']),
    ("1st St south to Garfield Circle", NEAR(38.8890, -77.0125, 'Garfield'), ['1st Street', 'Garfield']),
    ("Maryland Ave (mile 18)", IX('Maryland', '3rd Street', 38.8882, -77.0152), ['Maryland']),
    ("3rd St to Jefferson Dr", IX('Jefferson Drive', '3rd Street', 38.8887, -77.0152), ['3rd Street']),
    ("Jefferson Dr west (mile 19)", IX('Jefferson Drive', '14th', 38.8886, -77.0320), ['Jefferson']),
    ("14th St south to bridge", NEAR(38.8800, -77.0370, '395 Express'), ['14th Street', '395 Express']),
    ("14th St Bridge HOV lanes (mile 20)", NEAR(38.8690, -77.0490, '395 Express'), ['395 Express']),
    ("Exit to S Eads St / Pork Chop Lot (mile 21)", NEAR(38.86745, -77.05410, 'Eads'), ['395 Express', 'Eads']),
    ("Pork Chop Lot loop, north side", NEAR(38.86795, -77.05210, 'Pentagon Access'), ['Pentagon Access']),
    ("Pork Chop Lot loop, south side", NEAR(38.86690, -77.05300, 'Pentagon Access'), ['Pentagon Access']),
    ("S Eads St south", IX('Eads', 'Army Navy', 38.8648, -77.0534), ['Pentagon Access', 'Eads']),
    ("Army Navy Dr", IX('Army Navy', '12th Street', 38.8628, -77.0517), ['Army Navy']),
    ("12th St S to Crystal Dr (mile 22)", IX('12th Street', 'Crystal', 38.8624, -77.0488), ['12th Street']),
    ("Crystal Dr south to 2121 Crystal Dr turnaround (mile 23)", NEAR(38.8540, -77.0493, 'Crystal'), ['Crystal']),
    ("Crystal Dr back north", IX('12th Street', 'Crystal', 38.8624, -77.0488), ['Crystal']),
    ("Long Bridge Dr north (mile 24)", NEAR(38.8700, -77.0465, 'Long Bridge'), ['12th Street', 'Long Bridge']),
    ("N Boundary Dr north along the lagoon (mile 25)", NEAR(38.8781, -77.0535, 'Boundary'), ['Boundary']),
    ("Pentagon Access Rd to Rt 110, Rt 110 north (mile 26)", IX('Marshall', 'Richmond', 38.8865, -77.0670), ['Pentagon Access', 'Richmond']),
    ("Marshall Dr", IX('Marshall', 'Access Road', 38.8880, -77.0677), ['Marshall']),
    ("Iwo Jima Access Rd to finish", NEAR(38.8891, -77.0681, 'Access Road'), ['Access Road']),
]

if __name__ == '__main__':
    nodes = [START]
    report = []
    for label, tgt, prefer in LEGS:
        p = g.path(nodes[-1], tgt, prefer=prefer)
        L = g.length(p)
        report.append((label, round(L)))
        nodes += p[1:]
    total = g.length(nodes)
    for lbl, L in report:
        print(f"{L:6d} m  {lbl}")
    print(f"TOTAL {total:.0f} m = {total / 1609.344:.2f} mi (certified 26.22 mi / 42,195 m)")
    json.dump(g.coords(nodes), open(DATA / 'route.json', 'w'))
    # per-edge bridge flag (edge i joins node i and i+1) - used to fix elevation over water
    flags = []
    for a, b in zip(nodes, nodes[1:]):
        fi = g.G[a][b].get('fi', -1)
        flags.append(1 if fi >= 0 and g.feats[fi]['properties'].get('level') == 'bridge' else 0)
    json.dump(flags, open(DATA / 'route_bridges.json', 'w'))
