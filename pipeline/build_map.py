"""Build a single, fully offline, mobile-friendly HTML map of the 2026 Marine Corps Marathon.

- Basemap: OpenStreetMap vector tiles (Protomaps build, ODbL), trimmed to course + closures + 1.5 mi, embedded.
- folium (Leaflet) map; Leaflet, pmtiles and protomaps-leaflet are inlined -> no network needed.
- Legend doubles as layer switch (route, mile markers, road closures, Metro).
- Interactive elevation chart docked at the bottom, linked both ways with the route.

Inputs (data/): mcm_small.pmtiles, newbox.json, route.json, closures.geojson, metro.geojson, elevation.json
Usage: python3 pipeline/build_map.py [out.html]   (default: index.html at the repo root)
"""
import base64
import json
import math
import os
import sys

import folium
from folium.elements import Element

from config import DATA, NODE_MODULES, SITE
HERE = str(DATA)
NM = str(NODE_MODULES)
BASEMAP = 'mcm_small.pmtiles'

ROUTE_BLUE = '#1f5bff'
RED = '#d7191c'
METRO_C = {'Red': '#BF0D3E', 'Orange': '#ED8B00', 'Silver': '#919D9D', 'Blue': '#009CDE', 'Yellow': '#FFD100',
           'Green': '#00B140'}
METRO_W = {'Yellow': 11, 'Orange': 11, 'Silver': 7.5, 'Blue': 4, 'Green': 5, 'Red': 5}  # concentric bands on shared track


def flag_svg(color):
    """Checkered flag on a pole (anchor = pole base)."""
    sq, cols, rows, x0, y0 = 4, 5, 4, 5, 2
    cells = ''.join(f'<rect x="{x0 + c * sq}" y="{y0 + r * sq}" width="{sq}" height="{sq}" fill="{color if (r + c) % 2 == 0 else "#fff"}"/>'
                    for r in range(rows) for c in range(cols))
    return (f'<svg width="30" height="34" viewBox="0 0 30 34" xmlns="http://www.w3.org/2000/svg">'
            f'<rect x="{x0}" y="{y0}" width="{cols * sq}" height="{rows * sq}" fill="#fff" stroke="#222" stroke-width="1.6"/>'
            f'{cells}<rect x="{x0}" y="{y0}" width="{cols * sq}" height="{rows * sq}" fill="none" stroke="#222" stroke-width="1.2"/>'
            f'<line x1="4" y1="1" x2="4" y2="33" stroke="#222" stroke-width="2.4" stroke-linecap="round"/></svg>')


def metro_car_svg(lines):
    """Front view of a rail car; the stripe shows the lines serving the station."""
    w = 12 / max(1, len(lines))
    stripe = ''.join(f'<rect x="{4 + i * w:.2f}" y="11.2" width="{w + 0.05:.2f}" height="2.2" fill="{METRO_C[l]}"/>'
                     for i, l in enumerate(lines))
    return ('<svg width="20" height="22" viewBox="0 0 20 22" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="2" y="1" width="16" height="17" rx="4" fill="#2b2f36" stroke="#fff" stroke-width="1.2"/>'
            '<rect x="4.2" y="3.2" width="11.6" height="6.4" rx="1.5" fill="#cfe6ff"/>'
            f'{stripe}'
            '<circle cx="6" cy="15.6" r="1.3" fill="#ffd54a"/><circle cx="14" cy="15.6" r="1.3" fill="#ffd54a"/>'
            '<rect x="4.5" y="18" width="3" height="2.6" rx=".6" fill="#2b2f36"/>'
            '<rect x="12.5" y="18" width="3" height="2.6" rx=".6" fill="#2b2f36"/></svg>')


RUNNER_SVG = ('<svg width="34" height="34" viewBox="0 0 34 34" xmlns="http://www.w3.org/2000/svg">'
              f'<circle cx="17" cy="17" r="15.5" fill="#fff" stroke="{ROUTE_BLUE}" stroke-width="2.5"/>'
              f'<g stroke="{ROUTE_BLUE}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" fill="none">'
              '<path d="M18.5 12.5 L15.5 18.5"/><path d="M17.6 14 L21.5 16.3 L23.6 14.6"/><path d="M17.6 14 L13.8 14.4 L11.8 16.8"/>'
              '<path d="M15.5 18.5 L18.8 21.2 L18 25.6"/><path d="M15.5 18.5 L12.9 22 L9.6 21.4"/></g>'
              f'<circle cx="20" cy="9.6" r="2.4" fill="{ROUTE_BLUE}"/></svg>')


def hav(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def mile_points(route, cert_m=42195.0):
    cum = [0.0]
    for a, b in zip(route, route[1:]):
        cum.append(cum[-1] + hav(a, b))
    scale = cert_m / cum[-1]
    out, i = [], 1
    for m in range(1, 27):
        d = m * 1609.344 / scale
        while i < len(cum) - 1 and cum[i] < d:
            i += 1
        f = (d - cum[i - 1]) / ((cum[i] - cum[i - 1]) or 1)
        a, b = route[i - 1], route[i]
        out.append((m, (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))))
    return out


CSS = """
/* Layout: full-screen map app - top bar with tabs, map, docked elevation chart; Logistics tab is a reading view */
:root{
  --bg:#f4f6f9; --panel:#ffffff; --fg:#161a21; --muted:#5b6474; --line:#dde2ea; --chip:#eceff5; --hover:#f1f4f9;
  --accent:#1f5bff; --accent-soft:rgba(31,91,255,.16); --closure:#d7191c; --gold:#e08a00; --gold-soft:rgba(255,170,0,.22);
  --warn-bg:#fff4e5; --warn-fg:#7a4300;
  --display:"Barlow Condensed","Arial Narrow",system-ui,sans-serif; --ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --top-h:52px; --chart-h:168px;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#11141a; --panel:#1a1f28; --fg:#e8ebf1; --muted:#9ba4b4; --line:#2c3341; --chip:#262d39; --hover:#232a35;
  --accent:#7196ff; --accent-soft:rgba(113,150,255,.22); --closure:#ff6464; --gold:#f2a640; --gold-soft:rgba(242,166,64,.25);
  --warn-bg:#3a2a12; --warn-fg:#ffd59a; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#11141a; --panel:#1a1f28; --fg:#e8ebf1; --muted:#9ba4b4; --line:#2c3341; --chip:#262d39; --hover:#232a35;
  --accent:#7196ff; --accent-soft:rgba(113,150,255,.22); --closure:#ff6464; --gold:#f2a640; --gold-soft:rgba(242,166,64,.25);
  --warn-bg:#3a2a12; --warn-fg:#ffd59a; color-scheme:dark}
html,body{margin:0;height:100%;overflow:hidden;font-family:var(--ui)}
body{background:var(--bg);color:var(--fg)}
#topbar{position:absolute;top:0;left:0;right:0;height:var(--top-h);z-index:1200;display:flex;align-items:center;gap:12px;
  padding:0 max(12px,env(safe-area-inset-right,0px)) 0 max(12px,env(safe-area-inset-left,0px));background:var(--panel);
  border-bottom:1px solid var(--line);box-sizing:border-box}
#topbar .brand{font:700 21px/1 var(--display);letter-spacing:.02em;text-transform:uppercase;white-space:nowrap;flex:1;min-width:0;
  overflow:hidden;text-overflow:ellipsis}
#topbar .brand span{color:var(--muted);font-weight:600}
.tabs{display:flex;background:var(--chip);border-radius:10px;padding:3px;gap:2px}
.tabs button{border:0;background:none;color:var(--muted);font:600 13.5px var(--ui);padding:7px 12px;border-radius:8px;cursor:pointer;white-space:nowrap}
.tabs button[aria-selected="true"]{background:var(--panel);color:var(--fg);box-shadow:0 1px 3px rgba(0,0,0,.15)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.folium-map{position:absolute!important;top:var(--top-h)!important;left:0!important;right:0!important;bottom:var(--chart-h)!important;width:auto!important;height:auto!important}
#mcm-legend{position:absolute;top:calc(var(--top-h) + 10px);right:max(10px,env(safe-area-inset-right,0px));z-index:1001;background:var(--panel);
  border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.25);width:272px;max-height:calc(100% - var(--top-h) - var(--chart-h) - 30px);overflow:auto;color:var(--fg)}
#mcm-legend .hdr{display:flex;align-items:center;justify-content:space-between;padding:9px 12px 4px;gap:8px}
#mcm-legend .ttl{font:700 16px/1.1 var(--display);letter-spacing:.04em;text-transform:uppercase}
#mcm-legend .ttl small{display:block;font:500 12px var(--ui);letter-spacing:0;text-transform:none;color:var(--muted);margin-top:2px}
.tog{border:0;background:var(--chip);color:var(--fg);border-radius:8px;font:600 12px var(--ui);padding:6px 9px;cursor:pointer;white-space:nowrap}
#mcm-legend .rows{padding:2px 6px 8px}
.lg-row{display:flex;align-items:center;gap:10px;width:100%;border:0;background:none;text-align:left;padding:8px 6px;border-radius:8px;
  cursor:pointer;font:500 13.5px var(--ui);color:var(--fg);min-height:40px}
.lg-row:hover{background:var(--hover)}
.lg-row .sw{flex:0 0 38px;display:flex;align-items:center;justify-content:center}
.lg-row .txt{flex:1;line-height:1.25}.lg-row .txt small{display:block;color:var(--muted);font-size:11.5px;font-weight:400}
.lg-row .chk{flex:0 0 18px;height:18px;box-sizing:border-box;border-radius:5px;border:2px solid var(--accent);background:var(--accent);position:relative}
.lg-row .chk:after{content:"";position:absolute;left:4px;top:0;width:5px;height:10px;border:solid var(--panel);border-width:0 2.5px 2.5px 0;transform:rotate(45deg)}
.lg-row.off{color:var(--muted)}.lg-row.off .sw{opacity:.35}.lg-row.off .chk{background:transparent;border-color:var(--line)}.lg-row.off .chk:after{display:none}
#mcm-legend .note{padding:0 12px 10px;font-size:11px;color:var(--muted);line-height:1.4}
#mcm-legend.collapsed{width:auto}#mcm-legend.collapsed .rows,#mcm-legend.collapsed .note,#mcm-legend.collapsed .ttl{display:none}
#mcm-legend.collapsed .hdr{padding:6px}
#elev{position:absolute;left:0;right:0;bottom:0;height:var(--chart-h);background:var(--panel);border-top:1px solid var(--line);z-index:1002;
  display:flex;flex-direction:column;user-select:none;-webkit-user-select:none;padding-bottom:env(safe-area-inset-bottom,0px);box-sizing:border-box}
#elev .bar{display:flex;align-items:center;gap:10px;padding:6px max(12px,env(safe-area-inset-right,0px)) 0 max(12px,env(safe-area-inset-left,0px));font-size:13px;min-height:26px}
#elev .bar b{font:700 15px var(--display);letter-spacing:.05em;text-transform:uppercase}
#elev .read{flex:1;color:var(--accent);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
#elev .stat{color:var(--muted);font-size:12px;white-space:nowrap}
#elev svg{flex:1;width:100%;display:block;touch-action:none;cursor:crosshair}
#elev svg .grid{stroke:var(--line)} #elev svg .lbl{fill:var(--muted);font:10.5px var(--ui)} #elev svg .tick{stroke:var(--muted)}
#elev svg .area{fill:var(--accent-soft)} #elev svg .prof{stroke:var(--accent);fill:none}
#elev svg .band{fill:var(--gold-soft)} #elev svg .hl{stroke:var(--gold);fill:none} #elev svg .hld{fill:var(--gold);stroke:var(--panel)}
#elev svg .cur{stroke:var(--accent)} #elev svg .curd{fill:var(--panel);stroke:var(--accent)}
body.chart-min{--chart-h:34px}body.chart-min #elev svg,body.chart-min #elev .stat{display:none}
.mile{background:#fff;border:2px solid #1f5bff;border-radius:10px;color:#1f5bff;font:700 11px/16px var(--ui);text-align:center;width:18px;height:16px}
.leaflet-tooltip,.leaflet-popup-content{font-family:var(--ui)} .leaflet-div-icon{background:none;border:0}
.leaflet-control-attribution{font-size:10px!important;line-height:1.4}
.z-low .metro-ic svg{transform:scale(.72);transform-origin:center}
.z-low .mile{transform:scale(.85)}
/* Logistics reading view */
#logi{position:absolute;top:var(--top-h);left:0;right:0;bottom:0;z-index:1150;overflow-y:auto;background:var(--bg);-webkit-overflow-scrolling:touch}
#logi .wrap{max-width:720px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));line-height:1.6;font-size:16px}
#logi h1{font:700 clamp(30px,6vw,42px)/1.02 var(--display);text-transform:uppercase;letter-spacing:.01em;margin:4px 0 0;text-wrap:balance}
#logi .lede{color:var(--muted);margin:0 0 18px;max-width:62ch}
#logi h2{font:700 23px/1.1 var(--display);text-transform:uppercase;letter-spacing:.03em;margin:34px 0 10px;text-wrap:balance;
  display:flex;align-items:center;gap:10px}
#logi h2:after{content:"";flex:1;height:1px;background:var(--line)}
#logi p{margin:0 0 12px;max-width:65ch}
#logi .eyebrow{font:600 12px var(--ui);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.glance{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:6px 0 4px}
.glance div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}
.glance b{display:block;font:700 26px/1.05 var(--display);font-variant-numeric:tabular-nums}
.glance span{font-size:12.5px;color:var(--muted);line-height:1.3;display:block}
.glance .key b{color:var(--accent)}
ol.steps{list-style:none;margin:0;padding:0;display:grid;gap:12px;counter-reset:st}
ol.steps li{counter-increment:st;display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;align-items:start}
ol.steps li:before{content:counter(st);width:30px;height:30px;border-radius:15px;background:var(--accent);color:var(--panel);
  font:700 16px/30px var(--display);text-align:center}
ol.steps li > div{min-width:0}
ol.steps .t{font-weight:700;display:block;font-variant-numeric:tabular-nums}
.stn{border:0;background:var(--chip);color:var(--fg);font:700 15px var(--ui);padding:1px 7px;border-radius:6px;cursor:pointer;white-space:nowrap}
.stn:hover{background:var(--accent-soft)}
.stn i{display:inline-block;width:9px;height:9px;border-radius:5px;background:#FFD100;margin-right:5px;font-style:normal;vertical-align:0}
.callout{background:var(--warn-bg);color:var(--warn-fg);border-radius:10px;padding:10px 14px;margin:12px 0;font-size:15px}
.callout b{color:inherit}
.tips{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:10px}
.tips div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}
.tips h3{margin:0 0 4px;font:700 18px var(--display);text-transform:uppercase;letter-spacing:.03em}
.tips p{font-size:15px;margin:0}
dl.miles{margin:0;display:grid;gap:10px}
dl.miles > div{display:grid;grid-template-columns:150px minmax(0,1fr);gap:14px;padding:12px 14px;background:var(--panel);
  border:1px solid var(--line);border-radius:10px}
dl.miles dt{white-space:nowrap;font:700 19px/1.15 var(--display);text-transform:uppercase;letter-spacing:.02em;color:var(--accent);font-variant-numeric:tabular-nums}
dl.miles dd{margin:0;max-width:62ch}
#logi .src{font-size:12.5px;color:var(--muted);margin-top:32px;border-top:1px solid var(--line);padding-top:12px}
#logi a{color:var(--accent)}
@media (max-width:640px){
  :root{--chart-h:138px;--top-h:50px}
  #topbar .brand span{display:none}
  .tabs button{padding:7px 10px;font-size:13px}
  #mcm-legend{width:min(84vw,300px)}
  #elev .stat{display:none}
  .leaflet-control-scale{display:none}
  .lg-row{min-height:44px;font-size:14px}
  .glance{grid-template-columns:repeat(2,minmax(0,1fr))}
  dl.miles > div{grid-template-columns:1fr;gap:4px}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

TOPBAR = """
<div id="topbar">
  <div class="brand">MCM 2026 <span>&middot; Race Map</span></div>
  <div class="tabs" role="tablist" aria-label="Views">
    <button role="tab" data-tab="map" aria-selected="true">Map</button>
    <button role="tab" data-tab="logistics" aria-selected="false">Logistics</button>
  </div>
</div>"""

YL = '<i aria-hidden="true"></i>'


def stn(name, label):
    return f'<button class="stn" data-stn="{name}">{YL}{label}</button>'


MVS, PNT = stn('Mount Vernon Square', 'Mt. Vernon Sq'), stn('Pentagon', 'Pentagon')
LOGISTICS = f"""
<div id="logi" hidden>
 <div class="wrap">
  <h1>Logistical considerations</h1>

  <h2>Getting to the start</h2>
  <ol class="steps">
    <li><div><span class="t">Drive or Uber to {MVS} Metro station</span>
      I would recommend driving or Ubering to {MVS} Metro station. Anticipate potentially a longer drive, with road closures along
      Canal Rd, the GW Parkway, and the Clara Barton Parkway. I would recommend taking Connecticut Ave into the city.</div></li>
    <li><div><span class="t">Take the Yellow Line from {MVS} to {PNT}</span>
      From {MVS} station, take the Yellow Line from {MVS} to {PNT} in the Huntington direction.
      <div class="callout">Note: do not take a Green Line train to Branch Ave. Those do not go to the <b>Pentagon</b> station.</div></div></li>
    <li><div><span class="t">Arrive at {MVS} at 5:30 AM</span>
      With trains running every 15 min and it being a ~20 min ride, I would recommend arriving at {MVS} station at 5:30 AM.</div></li>
    <li><div><span class="t">Get to {PNT} around 6:10 AM</span>
      This will drop you off at {PNT} station at around 6:10 AM. This might seem like a lot of time, but there will be lines for
      everything (Metro escalators, porta-potties, bag drop-off), plus the ~1 mile walk to the start line.
      <b>Security is expected to take an extra <span style="white-space:nowrap">15&ndash;40 minutes</span>.</b></div></li>
    <li><div><span class="t">Use the walk to warm up</span>
      It might seem like a long walk, but that's the perfect opportunity to stretch, warm up, do some strides, and get the blood
      flowing to warm up your legs and core.</div></li>
  </ol>
  <p style="margin-top:14px"><b>Good to know:</b> Runners Village is in the Pentagon North parking lot, and everyone is screened by security on
  arrival. To get through security, you're required to have your bib on the front of you and your items in your clear plastic bag. Bag check uses the clear plastic bag from packet pickup with the sticker from the back of your bib; drop it at the UPS truck
  for your bib number and pick it up at the Finish Festival in Rosslyn (Wilson Blvd &amp; N. Lynn St).</p>

  <h2>What to wear</h2>
  <div class="tips">
    <div><h3>Throwaway layer</h3><p>I'd highly recommend an old hoodie/sweater you don't mind parting with at the start line, which people
      usually take off once the gun goes off and before they cross the start line. Volunteers come through to pick these up and donate them.</p></div>
    <div><h3>Gloves</h3><p>Also, gloves are huge! At the packet pickup, they should sell cheap ~$3 crappy gloves that do enough to keep your
      fingers from being unpleasantly frozen. I usually wear these for the first 5&ndash;6 miles until my hands start to get hot.</p></div>
    <div><h3>Socks</h3><p>Also, good socks are underrated and can prevent your feet from overheating and getting blisters, but I wouldn't
      change anything too drastic that you've not already done a long run in.</p></div>
  </div>

  <h2>What to expect during the race</h2>
  <p>This race is huge, so it's going to be packed. Especially if you're running at the ~3:30&ndash;4 hour pace mark, you're going to be in
  a lot of traffic. This can be pretty frustrating, especially for the first few miles when you feel like the field should have spread out
  by now. I expect you'll be stuck in a crowd until around mile 11, going past the Lincoln Memorial. But that also means you get to see a
  lot of fun characters (people juggling, wearing no shoes, wearing costumes). Also, don't mistake the lollipop sticks with gel on them that
  they hand out at the beginning for something to eat; they're Vaseline. I saw one guy make that mistake once.</p>

  <h2>Pacing</h2>
  <p><b>The most important thing to ensure your success is to make sure you start the race slower than you think you should, and keep your
  heart rate low.</b> All the factors at the beginning of the race will compound to raise your heart rate (being boxed in by the large crowd,
  needing to take extra steps to weave between people, the big hill at mile 2). Your legs are going to feel amazing and the adrenaline is
  going to push you to want to go faster, but holding back is key, because once your heart rate starts to creep up early, it's impossible to
  push it down, and that's only going to fatigue you later. Be especially wary of exerting yourself on that first hill; keep the effort
  consistent, even if it comes at the cost of speed going up the hill (it means you have a downhill you can blast down right after).</p>

  <h2>The course, mile by mile</h2>
  <dl class="miles">
    <div><dt>Miles 10&ndash;19</dt><dd>If you've managed to hold onto a good pace for the first 10 miles, miles 10&ndash;19 are what's worth
      the price of admission for this race. You get to go past all the monuments and museums, through Hains Point, and you have all the energy
      of everyone cheering! You should feel really good at this point, and miles 10&ndash;16 especially usually feel like you can run forever.
      If something goes wrong at this point though (fatigue, cramps, etc.), you're still more than halfway through the race, and the good vibes
      of being in a crowd can help push you through.</dd></div>
    <div><dt>Miles 19&ndash;22</dt><dd>Miles 19&ndash;22 are kinda boring, and the fatigue really starts to kick in here.</dd></div>
    <div><dt>Mile 23</dt><dd>Mile 23 through Crystal City is fun with everyone cheering for you, and that's where you turn around to head back
      to the Pentagon for the final stretch.</dd></div>
    <div><dt>Miles 24&ndash;26.2</dt><dd>Miles 24&ndash;26 are going to suck, but you'll find some gas to finish strong. Just remember there's a
      big hill for that last 0.2 miles going up to the finish line, so that's usually a good spot for a big kick to pass everyone else that's
      completely gassed. After that, you get your medal and a cool reflective blanket.</dd></div>
  </dl>

  <h2>Hydration and nutrition</h2>
  <p><b>Only eat what you've been training with.</b> I don't like to feel bloated when I start the race, so I usually have my last big meal
  be lunch the day before, and have some light dinner and snacks the evening of the day before. I then have a light breakfast (like a slice
  or two of toast, a banana, some coffee). Do whatever you're used to, though, and don't deviate too much from what your body is used to.</p>
  <p>I usually like to have my first gel/gummy packet at around mile 6, and then have them every 4&ndash;5 miles after. I don't bring water
  with me, although with the crowds, things will slow down at the aid stations (generally I aim for the last volunteers at the aid stations,
  since they will be generally pretty free and the crowd clears out by the time you get to them). I will at least stop at every other water
  stop, but especially at the end, I will grab water at each stop. I would avoid drinking too much water, and if I'm feeling hydrated
  (especially with the cool weather), I'll take a few sips and pour the rest to cool off.</p>
 </div>
</div>"""


def build(out_path):
    route = json.load(open(os.path.join(HERE, 'route.json')))
    closures = json.load(open(os.path.join(HERE, 'closures.geojson')))
    box = json.load(open(os.path.join(HERE, 'newbox.json')))
    metro = json.load(open(os.path.join(HERE, 'metro.geojson')))
    elev = json.load(open(os.path.join(HERE, 'elevation.json')))
    pm_b64 = base64.b64encode(open(os.path.join(HERE, BASEMAP), 'rb').read()).decode()

    m = folium.Map(location=(38.8880, -77.0560), zoom_start=13, tiles=None, control_scale=True,
                   max_zoom=18, min_zoom=12)
    m.default_js = []
    m.default_css = []
    root = m.get_root()
    head = root.header
    head.add_child(Element('<title>MCM 2026 Race Map</title>'), name='title')
    head.add_child(Element('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&display=swap">'),
                   name='fonts')
    head.add_child(Element('<style>' + open(f'{NM}/leaflet/dist/leaflet.css').read() + '</style>'), name='leaflet_css')
    head.add_child(Element('<script>' + open(f'{NM}/leaflet/dist/leaflet.js').read() + '</script>'), name='leaflet_js')
    head.add_child(Element('<script>' + open(f'{NM}/pmtiles/dist/pmtiles.js').read() + '</script>'), name='pmtiles_js')
    head.add_child(Element('<script>' + open(f'{NM}/protomaps-leaflet/dist/protomaps-leaflet.js').read() + '</script>'),
                   name='protomaps_js')
    head.add_child(Element('<style>' + CSS + '</style>'), name='mcm_css')
    # folium's popup template uses jQuery's $(html)[0]; a tiny shim avoids shipping jQuery
    head.add_child(Element('<script>window.$=window.$||function(h){const t=document.createElement("template");'
                           't.innerHTML=String(h).trim();return [t.content.firstElementChild];};</script>'), name='jq_shim')
    root.html.add_child(Element(f'<script id="mcm-pmtiles" type="application/octet-stream">{pm_b64}</script>'))

    # ---------------- Metrorail (bottom)
    metro_grp = folium.FeatureGroup(name='metro')
    for f in sorted([f for f in metro['features'] if f['properties']['kind'] == 'line'],
                    key=lambda f: -METRO_W[f['properties']['line']]):
        ln = f['properties']['line']
        folium.PolyLine([[(c[1], c[0]) for c in part] for part in f['geometry']['coordinates']],
                        color=METRO_C[ln], weight=METRO_W[ln], opacity=0.9, line_cap='butt',
                        tooltip=f'Metrorail {ln} Line').add_to(metro_grp)
    for f in metro['features']:
        if f['properties']['kind'] != 'station':
            continue
        lo, la = f['geometry']['coordinates']
        ls = f['properties']['lines']
        dots = ''.join(f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;background:{METRO_C[l]};'
                       f'margin-right:3px;vertical-align:-1px"></span>' for l in ls)
        html = f"<b>{f['properties']['name']}</b> Metro<br>{dots}{', '.join(ls)}"
        folium.Marker((la, lo), icon=folium.DivIcon(html=metro_car_svg(ls), icon_size=(20, 22), icon_anchor=(10, 11),
                                                     class_name='metro-ic'),
                      tooltip=folium.Tooltip(html), popup=folium.Popup(html, max_width=240)).add_to(metro_grp)

    # ---------------- race route
    course = folium.FeatureGroup(name='route')
    folium.PolyLine(route, color='#ffffff', weight=9, opacity=0.85, interactive=False).add_to(course)   # halo
    folium.PolyLine(route, color=ROUTE_BLUE, weight=5, opacity=0.95, interactive=False).add_to(course)
    start_html = '<b>START</b> &ndash; VA-110 northbound, between the Pentagon and Arlington Cemetery'
    finish_html = '<b>FINISH</b> &ndash; Marine Corps War Memorial (Iwo Jima Access Rd)'
    folium.Marker(route[0], icon=folium.DivIcon(html=flag_svg('#12a150'), icon_size=(30, 34), icon_anchor=(4, 33)),
                  tooltip=start_html, popup=folium.Popup(start_html, max_width=240), z_index_offset=1000).add_to(course)
    folium.Marker(route[-1], icon=folium.DivIcon(html=flag_svg(RED), icon_size=(30, 34), icon_anchor=(4, 33)),
                  tooltip=finish_html, popup=folium.Popup(finish_html, max_width=240), z_index_offset=1000).add_to(course)
    for pt, txt in [((38.88745, -77.03270), 'D.C. Gauntlet: 15th St &amp; Independence Ave by 12:33 PM'),
                    ((38.88520, -77.03210), 'Beat the Bridge: 14th &amp; D St SW, before the 14th St Bridge, by 1:15 PM (Mile 20)'),
                    ((38.86240, -77.04880), 'Crystal City Gauntlet: 12th St S &amp; Crystal Dr by 1:49 PM')]:
        folium.CircleMarker(pt, radius=7, color='#e08a00', fill=True, fill_color='#ffd27a', fill_opacity=1, weight=3,
                            tooltip=txt, popup=folium.Popup(txt, max_width=240)).add_to(course)
    milegrp = folium.FeatureGroup(name='miles')
    for mi, (la, lo) in mile_points(route):
        folium.Marker((la, lo), icon=folium.DivIcon(html=f'<div class="mile">{mi}</div>', icon_size=(22, 20),
                                                    icon_anchor=(11, 10)),
                      tooltip=f'Mile {mi} (approximate position)').add_to(milegrp)

    # ---------------- road closures: one layer
    clos = folium.FeatureGroup(name='closures')
    for f in closures['features']:
        p, g = f['properties'], f['geometry']
        src = ('Arlington 2026 closure list' if not p['group'].startswith('DC')
               else 'DC: from the 2025 list (no 2026 DC list published yet)')
        tip = f"<b>{p['desc']}</b><br>{p['window']}<br><span style='color:#777'>{src}</span>"
        if g['type'] == 'Point':
            t2 = tip + '<br>Ramp / interchange (location approximate)'
            folium.CircleMarker((g['coordinates'][1], g['coordinates'][0]), radius=7, color=RED, weight=2.5,
                                dash_array='3 3', fill=True, fill_color='#fff', fill_opacity=0.9,
                                tooltip=folium.Tooltip(t2), popup=folium.Popup(t2, max_width=260)).add_to(clos)
            continue
        parts = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
        folium.PolyLine([[(c[1], c[0]) for c in part] for part in parts], color=RED, weight=4, opacity=0.9,
                        dash_array='8 7', tooltip=folium.Tooltip(tip), popup=folium.Popup(tip, max_width=260)).add_to(clos)

    stations = {f['properties']['name']: [f['geometry']['coordinates'][1], f['geometry']['coordinates'][0]]
                for f in metro['features'] if f['properties']['kind'] == 'station'}
    metro_grp.add_to(m)
    course.add_to(m)
    clos.add_to(m)
    milegrp.add_to(m)

    ft = elev['ft']
    hi = max(ft)
    gain = sum(max(0, b - a) for a, b in zip(ft, ft[1:]))
    mi_hi = elev['mi'][ft.index(hi)]

    def sw_line(color, w, dash=''):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        return (f'<svg width="34" height="12"><line x1="1" y1="6" x2="33" y2="6" stroke="{color}" stroke-width="{w}"{d} '
                f'stroke-linecap="round"/></svg>')

    metro_sw = (f'<span style="display:inline-flex;align-items:center;gap:3px">{metro_car_svg(["Orange", "Silver", "Blue"])}'
                f'<span style="display:inline-flex;flex-direction:column;gap:1px">'
                + ''.join(f'<span style="width:9px;height:3px;background:{c}"></span>' for c in METRO_C.values())
                + '</span></span>')
    legend = TOPBAR + LOGISTICS + f"""
    <div id="mcm-legend">
      <div class="hdr"><div class="ttl">Map layers<small>Tap a row to show or hide it</small></div>
        <button class="tog" id="lg-tog" aria-expanded="true">Hide</button></div>
      <div class="rows">
        <button class="lg-row" data-layer="route" aria-pressed="true"><span class="sw">{sw_line(ROUTE_BLUE, 5)}</span>
          <span class="txt">Race route<small>Flags: green start, red finish; gauntlets</small></span><span class="chk"></span></button>
        <button class="lg-row" data-layer="miles" aria-pressed="true"><span class="sw"><span class="mile">13</span></span>
          <span class="txt">Mile markers<small>Approximate positions</small></span><span class="chk"></span></button>
        <button class="lg-row" data-layer="closures" aria-pressed="true"><span class="sw">{sw_line(RED, 4, '7 5')}</span>
          <span class="txt">Road closures<small>Tap a line for extent &amp; hours</small></span><span class="chk"></span></button>
        <button class="lg-row" data-layer="metro" aria-pressed="true"><span class="sw">{metro_sw}</span>
          <span class="txt">Metrorail lines &amp; stations<small>Check WMATA for race-day service</small></span><span class="chk"></span></button>
      </div>
      <div class="note">Arlington closures are the 2026 list; DC closures come from the 2025 list (no 2026 DC list yet).
        Times are approximate &ndash; confirm with official sources.</div>
    </div>
    <div id="elev">
      <div class="bar"><b>Elevation</b><span class="read" id="ev-read">Hover or drag along the chart</span>
        <span class="stat">High {hi:.0f} ft (mile {mi_hi:.1f}) &middot; climb &asymp;{gain:.0f} ft &middot;
          <span style="opacity:.75">USGS 3DEP terrain; bridge decks interpolated</span></span>
        <button class="tog" id="ev-tog">Hide</button></div>
      <svg id="ev-svg" aria-label="Course elevation profile"></svg>
    </div>"""
    root.html.add_child(Element(legend))

    js = r"""
    window.addEventListener('DOMContentLoaded', async function() {
      const map = MAPVAR;     // created by folium's script, which runs after this one is defined
      const E = ELEV;
      const N = E.mi.length, MAXMI = E.mi[N-1];
      // ---------------- basemap from embedded PMTiles
      const txt = document.getElementById('mcm-pmtiles').textContent;
      const bin = atob(txt.trim()); const u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      const buf = u8.buffer;
      document.getElementById('mcm-pmtiles').remove();
      class MemSource { getKey() { return 'mcm-embedded'; } async getBytes(o, l) { return { data: buf.slice(o, o + l) }; } }
      const pm = new pmtiles.PMTiles(new MemSource());
      const bounds = L.latLngBounds([BOX1, BOX0], [BOX3, BOX2]);
      const base = protomapsL.leafletLayer({url: pm, flavor: 'light', lang: 'en', maxDataZoom: 15, bounds,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="https://protomaps.com">Protomaps</a>'});
      base.addTo(map); base.bringToBack();
      map.setMaxBounds(bounds.pad(0.03));

      // ---------------- legend = layer switch
      const layers = {route: ROUTEGRP, miles: MILEGRP, closures: CLOSGRP, metro: METROGRP};
      const want = {route: true, miles: true, closures: true, metro: true};
      function syncMiles() {
        const show = want.miles && map.getZoom() >= 13;
        if (show && !map.hasLayer(layers.miles)) layers.miles.addTo(map);
        if (!show && map.hasLayer(layers.miles)) map.removeLayer(layers.miles);
      }
      document.querySelectorAll('.lg-row').forEach(btn => btn.addEventListener('click', () => {
        const k = btn.dataset.layer; want[k] = !want[k];
        btn.classList.toggle('off', !want[k]); btn.setAttribute('aria-pressed', want[k]);
        if (k === 'miles') syncMiles();
        else if (want[k]) layers[k].addTo(map); else map.removeLayer(layers[k]);
        if (k === 'route' && !want[k]) { runner.remove(); clearHi(); }
      }));
      const zoomClass = () => map.getContainer().classList.toggle('z-low', map.getZoom() < 14);
      map.on('zoomend', () => { syncMiles(); zoomClass(); }); syncMiles(); zoomClass();
      map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
      const lg = document.getElementById('mcm-legend'), lgt = document.getElementById('lg-tog');
      function setLegend(open) { lg.classList.toggle('collapsed', !open); lgt.textContent = open ? 'Hide' : 'Layers';
        lgt.setAttribute('aria-expanded', open); }
      lgt.addEventListener('click', () => setLegend(lg.classList.contains('collapsed')));
      if (window.matchMedia('(max-width: 640px)').matches) setLegend(false);
      const evt = document.getElementById('ev-tog');
      evt.addEventListener('click', () => { const min = document.body.classList.toggle('chart-min');
        evt.textContent = min ? 'Show' : 'Hide'; setTimeout(() => { map.invalidateSize(); draw(); }, 60); });

      // ---------------- elevation chart (SVG)
      const svg = document.getElementById('ev-svg'), read = document.getElementById('ev-read');
      const NS = 'http://www.w3.org/2000/svg';
      const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
      let W = 0, H = 0;
      const PL = 44, PR = 12, PT = 8, PB = 20, maxFt = Math.ceil(Math.max(...E.ft) / 50) * 50;
      const X = mi => PL + (mi / MAXMI) * (W - PL - PR);
      const Y = ft => PT + (1 - ft / maxFt) * (H - PT - PB);
      let gHi = null, gCur = null, lastCur = null;
      function draw() {
        const r = svg.getBoundingClientRect(); W = r.width; H = r.height; if (W < 10 || H < 10) return;
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.innerHTML = '';
        const small = W < 520;
        for (let f = 0; f <= maxFt; f += 100) {
          svg.appendChild(mk('line', {x1: PL, x2: W - PR, y1: Y(f), y2: Y(f), class: 'grid'}));
          const t = mk('text', {x: PL - 6, y: Y(f) + 4, 'text-anchor': 'end', class: 'lbl'}); t.textContent = f + ' ft'; svg.appendChild(t);
        }
        const step = small ? 5 : 2;
        for (let mi = 0; mi <= 26; mi += step) {
          svg.appendChild(mk('line', {x1: X(mi), x2: X(mi), y1: H - PB, y2: H - PB + 4, class: 'tick'}));
          const t = mk('text', {x: X(mi), y: H - 5, 'text-anchor': mi === 0 ? 'start' : 'middle', class: 'lbl'});
          t.textContent = mi === 0 ? '0 mi' : mi; svg.appendChild(t);
        }
        let line = '';
        for (let i = 0; i < N; i++) line += (i ? 'L' : 'M') + X(E.mi[i]).toFixed(1) + ',' + Y(E.ft[i]).toFixed(1);
        svg.appendChild(mk('path', {d: line + `L${X(MAXMI)},${Y(0)}L${X(0)},${Y(0)}Z`, class: 'area'}));
        svg.appendChild(mk('path', {d: line, class: 'prof', 'stroke-width': 2}));
        gHi = mk('g', {}); gCur = mk('g', {}); svg.appendChild(gHi); svg.appendChild(gCur);
        if (lastCur != null) cursor(lastCur);
        if (lastHi != null) highlight(lastHi);
      }
      new ResizeObserver(draw).observe(svg);

      // ---------------- runner on the route (chart -> map)
      const runner = L.marker([E.lat[0], E.lon[0]], {icon: L.divIcon({html: RUNNERSVG, className: '', iconSize: [34, 34], iconAnchor: [17, 17]}),
                                                     interactive: false, zIndexOffset: 2000, keyboard: false});
      const fmt = i => `Mile ${E.mi[i].toFixed(1)} · ${Math.round(E.ft[i])} ft`;
      function cursor(i) {
        lastCur = i; if (!gCur) return; gCur.innerHTML = '';
        gCur.appendChild(mk('line', {x1: X(E.mi[i]), x2: X(E.mi[i]), y1: PT, y2: H - PB, class: 'cur', 'stroke-width': 1.2, 'stroke-dasharray': '3 3'}));
        gCur.appendChild(mk('circle', {cx: X(E.mi[i]), cy: Y(E.ft[i]), r: 5, class: 'curd', 'stroke-width': 2.5}));
      }
      function idxAtX(clientX) {
        const r = svg.getBoundingClientRect(); const mi = ((clientX - r.left) - PL) / (W - PL - PR) * MAXMI;
        let lo = 0, hi = N - 1; while (lo < hi) { const m = (lo + hi) >> 1; if (E.mi[m] < mi) lo = m + 1; else hi = m; }
        return Math.max(0, Math.min(N - 1, lo));
      }
      function onChart(ev) {
        const i = idxAtX(ev.clientX); cursor(i); read.textContent = fmt(i);
        if (!want.route) return;
        runner.setLatLng([E.lat[i], E.lon[i]]); if (!map.hasLayer(runner)) runner.addTo(map);
        if (!map.getBounds().pad(-0.08).contains(runner.getLatLng())) map.panTo(runner.getLatLng(), {animate: ev.pointerType !== 'mouse'});
      }
      svg.addEventListener('pointerdown', ev => { try { svg.setPointerCapture(ev.pointerId); } catch (_) {} onChart(ev); });
      svg.addEventListener('pointermove', ev => { if (ev.pointerType === 'mouse' || ev.buttons) onChart(ev); });
      svg.addEventListener('pointerleave', ev => { if (ev.pointerType !== 'mouse') return;
        runner.remove(); if (gCur) gCur.innerHTML = ''; lastCur = null; if (lastHi == null) read.textContent = 'Hover or drag along the chart'; });

      // ---------------- route hover / tap (map -> chart)
      const cosLat = Math.cos(38.89 * Math.PI / 180);
      function nearestIdx(ll) {
        let best = 0, bd = Infinity;
        for (let i = 0; i < N; i++) { const dy = E.lat[i] - ll.lat, dx = (E.lon[i] - ll.lng) * cosLat, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } }
        return best;
      }
      const dot = L.circleMarker([E.lat[0], E.lon[0]], {radius: 6, color: '#e08a00', weight: 3, fillColor: '#fff', fillOpacity: 1, interactive: false});
      let lastHi = null;
      function highlight(i) {
        lastHi = i; read.textContent = fmt(i); if (!gHi) return; gHi.innerHTML = '';
        const half = 0.35, a = Math.max(0, E.mi[i] - half), b = Math.min(MAXMI, E.mi[i] + half);
        gHi.appendChild(mk('rect', {x: X(a), y: PT, width: X(b) - X(a), height: H - PT - PB, class: 'band'}));
        let d = ''; for (let k = 0; k < N; k++) if (E.mi[k] >= a && E.mi[k] <= b) d += (d ? 'L' : 'M') + X(E.mi[k]).toFixed(1) + ',' + Y(E.ft[k]).toFixed(1);
        gHi.appendChild(mk('path', {d, class: 'hl', 'stroke-width': 3.5}));
        gHi.appendChild(mk('circle', {cx: X(E.mi[i]), cy: Y(E.ft[i]), r: 5, class: 'hld', 'stroke-width': 2}));
      }
      function clearHi() { lastHi = null; if (gHi) gHi.innerHTML = ''; dot.remove(); if (lastCur == null) read.textContent = 'Hover or drag along the chart'; }
      function showAt(ll) { const i = nearestIdx(ll); highlight(i); dot.setLatLng([E.lat[i], E.lon[i]]); if (!map.hasLayer(dot)) dot.addTo(map); }
      // proximity test at map level, so it also works where closures are drawn over the course
      function nearRoute(e, px) {
        if (!want.route) return -1;
        const i = nearestIdx(e.latlng);
        const p = map.latLngToContainerPoint([E.lat[i], E.lon[i]]);
        return p.distanceTo(e.containerPoint) <= px ? i : -1;
      }
      const canHover = window.matchMedia('(hover: hover)').matches;   // touch screens: tap only
      if (canHover) {
        map.on('mousemove', e => { const i = nearRoute(e, 14); if (i >= 0) showAt(e.latlng); else if (lastHi != null) clearHi(); });
        map.on('mouseout', () => { if (lastHi != null) clearHi(); });
      }
      map.on('click', e => { const i = nearRoute(e, 22); if (i >= 0) showAt(e.latlng); else clearHi(); });
      // ---------------- tabs (Map / Logistics), deep-linkable as #map and #logistics
      const logi = document.getElementById('logi');
      const tabBtns = document.querySelectorAll('.tabs button');
      function showTab(name) {
        const isLog = name === 'logistics';
        logi.hidden = !isLog;
        tabBtns.forEach(b => b.setAttribute('aria-selected', b.dataset.tab === (isLog ? 'logistics' : 'map')));
        if (!isLog) setTimeout(() => { map.invalidateSize(); draw(); }, 30);
        try { history.replaceState(null, '', '#' + (isLog ? 'logistics' : 'map')); } catch (_) {}
      }
      tabBtns.forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
      const STN = STATIONS;
      const ring = L.circleMarker([0, 0], {radius: 18, color: '#1f5bff', weight: 3, fill: false, interactive: false});
      document.querySelectorAll('[data-stn]').forEach(b => b.addEventListener('click', () => {
        const p = STN[b.dataset.stn]; if (!p) return;
        showTab('map'); if (!want.metro) document.querySelector('.lg-row[data-layer=metro]').click();
        setTimeout(() => { map.setView(p, 16, {animate: false}); ring.setLatLng(p).addTo(map); setTimeout(() => ring.remove(), 4000); }, 60);
      }));
      showTab(location.hash === '#logistics' ? 'logistics' : 'map');
      requestAnimationFrame(() => { map.invalidateSize(); draw(); });
      window.mcmReady = true;
    });
    """
    js = (js.replace('MAPVAR', m.get_name()).replace('ELEV', json.dumps(elev, separators=(',', ':')))
            .replace('BOX0', str(box[0])).replace('BOX1', str(box[1])).replace('BOX2', str(box[2])).replace('BOX3', str(box[3]))
            .replace('STATIONS', json.dumps(stations))
            .replace('ROUTEGRP', course.get_name()).replace('MILEGRP', milegrp.get_name())
            .replace('CLOSGRP', clos.get_name()).replace('METROGRP', metro_grp.get_name())
            .replace('RUNNERSVG', json.dumps(RUNNER_SVG)))
    root.script.add_child(Element(js))
    m.fit_bounds([[38.852, -77.100], [38.923, -77.008]])
    m.save(out_path)
    print(f"saved {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB); high {hi:.0f} ft at mile {mi_hi:.1f}; gain {gain:.0f} ft")


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else str(SITE))
