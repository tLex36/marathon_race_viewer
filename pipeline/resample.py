"""Resample the traced route every 40 m (with a bridge flag per sample) and work out where the bridge abutments are.

Outputs: data/samples.json   [[lat, lon, on_bridge, metres_from_start], ...]
         data/bridge_probes.json {"runs": [[i0, i1], ...], "probes": [[lat, lon], ...]}
"""
import json
import math
from config import DATA

STEP = 40.0
route = json.load(open(DATA / 'route.json'))
flags = json.load(open(DATA / 'route_bridges.json'))


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


cum = [0.0]
for a, b in zip(route, route[1:]):
    cum.append(cum[-1] + hav(a, b))
T = cum[-1]
samples, j = [], 0
for k in range(int(T // STEP) + 2):
    d = min(k * STEP, T)
    while j < len(cum) - 2 and cum[j + 1] < d:
        j += 1
    f = (d - cum[j]) / ((cum[j + 1] - cum[j]) or 1)
    a, b = route[j], route[j + 1]
    samples.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), flags[j], d))
    if d >= T:
        break
json.dump(samples, open(DATA / 'samples.json', 'w'))

# bridge runs: consecutive bridge samples, allowing gaps of up to 2 samples
fl = [s[2] for s in samples]
runs, i, n = [], 0, len(samples)
while i < n:
    if fl[i]:
        j = i
        while j + 1 < n and (fl[j + 1] or (j + 2 < n and fl[j + 2]) or (j + 3 < n and fl[j + 3])):
            j += 1
        while not fl[j]:
            j -= 1
        runs.append([i, j])
        i = j + 1
    else:
        i += 1


def beyond(p, q, d=40.0):
    """Point d metres past p, continuing the direction q -> p."""
    dy, dx = p[0] - q[0], p[1] - q[1]
    L = math.hypot(dy * 111000, dx * 111000 * math.cos(math.radians(38.89))) or 1
    return [p[0] + dy * d / L, p[1] + dx * d / L]


probes = []
for a, b in runs:
    if b - a >= 1:
        probes.append(beyond(samples[a][:2], samples[min(a + 1, b)][:2]))
        probes.append(beyond(samples[b][:2], samples[max(b - 1, a)][:2]))
json.dump({'runs': runs, 'probes': probes}, open(DATA / 'bridge_probes.json', 'w'))
print(f"{len(samples)} samples over {T / 1000:.2f} km; {len(runs)} bridge runs; {len(probes)} abutment probes")
