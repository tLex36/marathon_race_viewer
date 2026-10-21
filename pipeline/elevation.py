"""Clean the raw terrain profile -> data/elevation.json (miles and feet along the course).

Bare-earth terrain reads the river surface under a bridge deck, so each bridge run is interpolated between
its abutments (terrain 40 m beyond each end). Key Bridge is special: the course climbs the GW Parkway on-ramp
to meet the deck at Rosslyn street level, so its Rosslyn end uses N Lynn St and the ramp is graded up to it.
Isolated pits under overpasses are median-filtered, then the profile is lightly smoothed (200 m window).
"""
import json
import math
import statistics
from config import DATA

CERT_MI = 26.219                      # USATF-certified course length
KEY_BRIDGE_S = (38.9006, -77.0707)    # south (Rosslyn) end of Key Bridge
RAMP_SAMPLES = 8                      # ~320 m on-ramp graded up to the deck

s = json.load(open(DATA / 'samples.json'))
e = json.load(open(DATA / 'elev_raw.json'))
runs = json.load(open(DATA / 'bridge_probes.json'))['runs']
pe = json.load(open(DATA / 'probe_elev.json'))
probe_vals, lynn = pe['probes'], pe['lynn_st']


def near(i, p, m=150):
    return math.hypot((s[i][0] - p[0]) * 111000, (s[i][1] - p[1]) * 111000 * math.cos(math.radians(38.89))) < m


k = 0
for a, b in runs:
    if b - a < 1:
        e[a] = (e[a - 1] + e[b + 1]) / 2
        continue
    L = max(probe_vals[k], e[a - 1]); R = max(probe_vals[k + 1], e[b + 1]); k += 2
    if near(a, KEY_BRIDGE_S):
        L = lynn
        r0 = a - RAMP_SAMPLES
        for i in range(r0, a):
            e[i] = e[r0] + (L - e[r0]) * (i - r0) / (a - r0)
    for i in range(a, b + 1):
        e[i] = L + (R - L) * (i - a + 1) / (b - a + 2)

med = [statistics.median(e[max(0, i - 2):i + 3]) for i in range(len(e))]
sm = [sum(med[max(0, i - 2):i + 3]) / len(med[max(0, i - 2):i + 3]) for i in range(len(med))]
T = s[-1][3]
out = {"mi": [round(x[3] / T * CERT_MI, 3) for x in s], "ft": [round(v * 3.28084, 1) for v in sm],
       "lat": [round(x[0], 6) for x in s], "lon": [round(x[1], 6) for x in s]}
json.dump(out, open(DATA / 'elevation.json', 'w'))
ft = out['ft']
gain = sum(max(0, b - a) for a, b in zip(ft, ft[1:]))
print(f"high {max(ft):.0f} ft at mile {out['mi'][ft.index(max(ft))]:.1f}; start {ft[0]:.0f}; finish {ft[-1]:.0f}; climb {gain:.0f} ft")
