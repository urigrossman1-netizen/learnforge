"""Assemble rendered systems into a self-contained, zoomable, theme-aware HTML page."""
from __future__ import annotations

import html
import os
from typing import Dict, List

from .engrave import (GLYPHS, Canvas, RenderedSystem, f, glyph_defs, gw, head_width, layout_chart,
                      render_system, ypos, anchor, STEM, LEDGER, LEDGER_EXT, STAFF_LINE, section_id,
                      tempo_parts, tempo_html)
from .model import INSTRUMENTS, STAFF_STYLE, Chart, staff_key
from .notation import HEAD_OVERRIDES

LAYOUTS = (4, 2, 1)
CONTENT_W = {4: 124.0, 2: 66.0, 1: 37.0}


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _fmt_time(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# ---------------------------------------------------------------------------
# Drum key (legend) — one mini staff per instrument / technique used
# ---------------------------------------------------------------------------
def _legend_items(chart: Chart) -> List[tuple]:
    """Instruments (low to high, as in printed drum keys) then techniques actually used."""
    used = {}
    for b in chart.bars:
        for h in b.hits:
            if h.inst in INSTRUMENTS:
                used.setdefault(h.inst, set()).add(h.art)
    items = []
    for code in sorted(used, key=lambda c: (INSTRUMENTS[c].pos, -INSTRUMENTS[c].order)):
        items.append((code, "x", INSTRUMENTS[code].name))
    tech = [
        ("SN", "c", "Rim click (cross-stick)"), ("SN", "r", "Rimshot"), ("RD", "b", "Ride bell"), ("R2", "b", "Ride 2 bell"),
        ("HH", "o", "Open hi-hat"), ("HH", "h", "Half-open"), ("HF", "o", "Hi-hat splash"),
    ]
    for code, a, lab in tech:
        arts = used.get(code, set())
        if a in arts or a.upper() in arts:
            items.append((code, a, lab))
        if code == "HH" and a == "h" and arts & set("oOh") and STAFF_STYLE["open_marks"]:
            items.append(("HH", "+", "Closed (after open)"))
    if any(a == "g" for arts in used.values() for a in arts):
        items.append(("SN", "g", "Ghost note"))
    if any(a in "XOFBR" for arts in used.values() for a in arts):
        items.append(("SN", "X", "Accent"))
    if any(a in "fF" for arts in used.values() for a in arts):
        items.append(("SN", "f", "Flam"))
    if any(a == "d" for arts in used.values() for a in arts):
        items.append(("SN", "d", "Drag"))
    if any(a == "z" for arts in used.values() for a in arts):
        items.append(("SN", "z", "Buzz roll"))
    if any(a == "k" for arts in used.values() for a in arts):
        items.append(("CR", "k", "Choked cymbal"))
    return items


def legend_svg(code: str, art: str) -> str:
    from .notation import build_notehead
    from .engrave import _grace
    I = INSTRUMENTS[code]
    nh = build_notehead(code, art)
    head = nh.head
    cv = Canvas()
    W = 5.6
    for k in range(5):
        cv.line(0, k, W, k, STAFF_LINE, "staff")
    hw = head_width(head)
    x_on = W / 2 + (0.4 if (nh.flam or nh.drag) else 0)
    y = ypos(I.pos)
    up = I.voice == "up"
    stem_x = x_on + 0.59 if up else x_on - 0.59
    if up:
        ax, ay = anchor(head, "stemUpSE", (hw, -0.168))
    else:
        ax, ay = anchor(head, "stemDownNW", (0.0, 0.168))
    xl = stem_x - ax
    if I.pos >= 10:
        for lp in range(10, I.pos + 1, 2):
            cv.line(xl - LEDGER_EXT, ypos(lp), xl + hw + LEDGER_EXT, ypos(lp), LEDGER, "ink-stroke")
    if I.pos <= -2:
        for lp in range(-2, I.pos - 1, -2):
            cv.line(xl - LEDGER_EXT, ypos(lp), xl + hw + LEDGER_EXT, ypos(lp), LEDGER, "ink-stroke")
    cv.glyph(head, xl, y)
    if nh.ghost:
        cv.glyph("noteheadParenthesisLeft", xl - 0.382, y)
        cv.glyph("noteheadParenthesisRight", xl + hw + 0.078, y)
    if nh.flam or nh.drag:
        _grace(cv, nh, xl, y, drag=nh.drag)
    if nh.choke and STAFF_STYLE["choke"] == "pict":
        cv.glyph("pictChokeCymbal", xl + hw + 0.15, y - 0.35)
    top = min(y - 3.3, -1.0)
    if up:
        cv.rect(stem_x - STEM, top, STEM, (y + ay) - top, "ink")
        if nh.buzz:
            cv.glyph("buzzRoll", stem_x - STEM / 2 - gw("buzzRoll") / 2, (y + top) / 2 + 0.45)
        mark = "pictOpen" if (code == "HH" and nh.open and STAFF_STYLE["open_marks"]) else (
            "pictHalfOpen2" if nh.half else None)
        if code == "HH" and art == "+":
            mark = "pictOpenRimShot"
        yy = top - 0.45
        if nh.choke and STAFF_STYLE["choke"] == "dot":
            cv.glyph("articStaccatoAbove", stem_x - STEM / 2 - gw("articStaccatoAbove") / 2, yy)
            yy -= 1.0
        if nh.accent:
            cv.glyph("articAccentAbove", stem_x - STEM / 2 - gw("articAccentAbove") / 2, yy)
            yy -= 1.35
        if mark:
            cv.glyph(mark, stem_x - STEM / 2 - gw(mark) / 2, yy)
    else:
        bot = max(y + 3.3, 5.0)
        cv.rect(stem_x, y + ay, STEM, bot - (y + ay), "ink")
        if code == "HF" and nh.open and STAFF_STYLE["open_marks"]:
            bb = GLYPHS["pictOpen"]["bbox"]
            cv.glyph("pictOpen", stem_x + STEM / 2 - gw("pictOpen") / 2, bot + 0.45 - bb[1])
    y0, y1 = min(cv.ymin, -5.2) - 0.3, max(cv.ymax, 7.2) + 0.3
    return (f'<svg class="key-svg" viewBox="0 {f(y0)} {f(W)} {f(y1 - y0)}" style="--w:{f(W)}" aria-hidden="true">'
            + "".join(cv.items) + "</svg>")


GRID_KEY = [
    ("hit", "Hit"), ("accent", "Accent"), ("ghost", "Ghost note"), ("open", "Open hi-hat"),
    ("flam", "Flam"), ("cross", "Cross-stick"), ("bell", "Ride bell"), ("buzz", "Buzz roll"),
]


def grid_key_svg(kind: str) -> str:
    c = "m-snr" if kind in ("hit", "accent", "ghost", "flam", "buzz", "cross") else "m-cym"
    x, y = 1.6, 1.0
    if kind == "hit":
        s = f'<rect x="{f(x - .56)}" y="{f(y - .56)}" width="1.12" height="1.12" rx="0.28" class="{c}"/>'
    elif kind == "accent":
        s = f'<rect x="{f(x - .7)}" y="{f(y - .7)}" width="1.4" height="1.4" rx="0.3" class="{c} accent-mark"/>'
    elif kind == "ghost":
        s = f'<rect x="{f(x - .41)}" y="{f(y - .41)}" width="0.82" height="0.82" rx="0.22" class="{c} ghost-mark"/>'
    elif kind == "open":
        s = f'<circle cx="{f(x)}" cy="{f(y)}" r="0.5" class="{c} open-mark"/>'
    elif kind == "flam":
        s = (f'<rect x="{f(x - .56 - .7)}" y="{f(y - .3)}" width="0.6" height="0.6" rx="0.18" class="{c}"/>'
             f'<rect x="{f(x - .56)}" y="{f(y - .56)}" width="1.12" height="1.12" rx="0.28" class="{c}"/>')
    elif kind == "cross":
        d = 0.48
        s = (f'<path d="M{f(x - d)} {f(y - d)} L{f(x + d)} {f(y + d)} M{f(x + d)} {f(y - d)} L{f(x - d)} {f(y + d)}" '
             f'class="{c}-stroke" stroke-width="0.3" stroke-linecap="round"/>')
    elif kind == "bell":
        r = 0.66
        s = f'<polygon points="{f(x)},{f(y - r)} {f(x + r)},{f(y)} {f(x)},{f(y + r)} {f(x - r)},{f(y)}" class="{c}"/>'
    else:  # buzz
        s = f'<rect x="{f(x - .56)}" y="{f(y - .32)}" width="2.4" height="0.64" rx="0.32" class="{c}"/>'
    return f'<svg class="gk-svg" viewBox="0 0 4 2" aria-hidden="true">{s}</svg>'


# ---------------------------------------------------------------------------
CSS = r"""
/* Layout: a gig chart on a music stand — one wide reading column of systems,
   a slim sticky control bar, the song's road map up top. */
:root{
  --paper:#fbfbfa; --paper-2:#f2f2ef; --ink:#121317; --ink-2:#4d4f57; --ink-3:#85868c;
  --rule:#d9d9d4; --band:rgba(18,19,23,.045); --chip:#121317; --chip-ink:#fbfbfa;
  --cym:#eda100; --snr:#e87ba4; --tom:#008300; --kik:#2a78d6; --neu:#898781;
  --warn:#fab219; --warn-ink:#8a5a00; --low:#d03b3b; --hl:rgba(42,120,214,.12);
  --f-display:"Archivo","Arial Narrow","Helvetica Neue",Arial,sans-serif;
  --f-body:"Atkinson Hyperlegible","Segoe UI",system-ui,-apple-system,sans-serif;
  --f-music:"EB Garamond","Iowan Old Style","Palatino Linotype",Georgia,serif;
  --sp:9;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#18181a; --paper-2:#222226; --ink:#f1f1ee; --ink-2:#c3c2bc; --ink-3:#8d8c88;
    --rule:#36363a; --band:rgba(255,255,255,.05); --chip:#f1f1ee; --chip-ink:#18181a;
    --cym:#c98500; --snr:#d55181; --tom:#2f9e44; --kik:#3987e5; --neu:#898781;
    --warn:#fab219; --warn-ink:#fab219; --low:#e66767; --hl:rgba(57,135,229,.22); color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --paper:#18181a; --paper-2:#222226; --ink:#f1f1ee; --ink-2:#c3c2bc; --ink-3:#8d8c88;
  --rule:#36363a; --band:rgba(255,255,255,.05); --chip:#f1f1ee; --chip-ink:#18181a;
  --cym:#c98500; --snr:#d55181; --tom:#2f9e44; --kik:#3987e5; --neu:#898781;
  --warn:#fab219; --warn-ink:#fab219; --low:#e66767; --hl:rgba(57,135,229,.22); color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--f-body);font-size:15px;line-height:1.5}
.wrap{max-width:1320px;margin:0 auto;padding-inline:clamp(16px,3vw,40px);padding-block:28px 64px}
a{color:inherit}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:4px}

/* masthead */
.mast{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 32px;align-items:end;border-bottom:2px solid var(--ink);padding-bottom:14px}
.eyebrow{font:600 12px/1 var(--f-body);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2)}
h1{font-family:var(--f-display);font-stretch:72%;font-weight:800;font-size:clamp(38px,6vw,68px);line-height:.95;letter-spacing:-.01em;margin:8px 0 6px;text-wrap:balance}
.byline{margin:0;color:var(--ink-2);font-size:16px}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0;justify-content:flex-end}
.facts div{display:flex;flex-direction:column;align-items:flex-start}
.facts dt{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
.facts dd{margin:0;font:700 19px/1.2 var(--f-display);font-stretch:85%;font-variant-numeric:tabular-nums}
@media (max-width:760px){.mast{grid-template-columns:1fr}.facts{justify-content:flex-start}}

/* toolbar */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);border-bottom:1px solid var(--rule);
  display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:10px 0;margin-bottom:6px}
.grp{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.grp-label{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin-right:4px}
button,.tog{font:600 13px/1 var(--f-body);color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:7px;
  padding:8px 11px;cursor:pointer;min-height:34px}
button:hover,.tog:hover{border-color:var(--ink-3)}
button[aria-pressed="true"]{background:var(--chip);color:var(--chip-ink);border-color:var(--chip)}
#zoomPct{min-width:56px;text-align:center;font-variant-numeric:tabular-nums}
.spacer{flex:1}
.hint{font-size:12px;color:var(--ink-3)}
@media (max-width:700px){
  .bar{gap:6px 10px;padding:8px 0;position:static}
  .bar .hint,.grp-label{display:none}
  button,.tog,select{padding:7px 9px;min-height:32px;font-size:12.5px}
}

/* road map */
.road{margin:18px 0 8px}
.road h2,.key h2,.notes h2{font:700 13px/1 var(--f-body);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2);margin:0 0 10px}
.road ol{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.road a{display:flex;align-items:baseline;gap:8px;text-decoration:none;border:1px solid var(--rule);border-radius:7px;padding:6px 10px;background:var(--paper)}
.road a:hover{border-color:var(--ink)}
.road .nm{font:700 14px/1.1 var(--f-display);font-stretch:80%;text-transform:uppercase;letter-spacing:.03em}
.road .mk{font:800 12px/1 var(--f-display);background:var(--chip);color:var(--chip-ink);border-radius:3px;padding:3px 5px}
.road .ct{font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.road .q{width:7px;height:7px;border-radius:50%;background:var(--warn);align-self:center}

/* key */
.key{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:18px 36px;margin:22px 0 10px;padding:16px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
@media (max-width:860px){.key{grid-template-columns:1fr}}
.key ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:4px 6px}
.key li{display:flex;flex-direction:column;align-items:center;width:76px}
.key-svg{width:calc(var(--w) * 8px);height:auto;color:var(--ink)}
.key li span{font-size:12px;line-height:1.2;text-align:center;color:var(--ink-2)}
.gk{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:6px 10px}
.gk div{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--ink-2)}
.gk-svg{width:40px;height:20px}
.fam{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-size:13px;color:var(--ink-2)}
.fam i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}

/* chart */
.chart{overflow-x:auto;padding-bottom:8px}
.layout{display:none}
.layout.on{display:block}
.sys{margin:0 0 calc(var(--sp) * 1.2px);break-inside:avoid;page-break-inside:avoid;width:calc(var(--w) * var(--sp) * 1px);max-width:none}
body.fitmode .sys{max-width:100%}
.sys.sec-start{margin-top:calc(var(--sp) * 1.6px)}
.sys > svg{display:block;height:auto;width:100%;color:var(--ink);overflow:visible}
.counts-svg,.grid-svg{margin-top:2px}
body.no-grid .grid-svg{display:none}
body.no-counts .counts-svg{display:none}
body.focus .mast,body.focus .road,body.focus .key,body.focus .notes{display:none}

/* svg ink */
.ink,svg use{fill:var(--ink)}
.ink-stroke,.staff{stroke:var(--ink)}
.staff{stroke:var(--ink);opacity:.9}
use.rest{fill:var(--ink)}
use.ghost{fill:var(--ink)}
use.grace{fill:var(--ink)}
text{fill:var(--ink);font-family:var(--f-body)}
text.tempo{font-weight:700}
.cue{font-family:var(--f-music);font-style:italic;fill:var(--ink)}
.barnum{fill:var(--ink-3);font-style:italic;font-family:var(--f-music)}
.simile-num{fill:var(--ink-3);font-weight:700}
.sticking{font-weight:700;fill:var(--ink-2)}
.conf-medium{fill:none;stroke:var(--warn);stroke-width:.14;stroke-dasharray:.5 .35}
.conf-low{fill:none;stroke:var(--low);stroke-width:.16;stroke-dasharray:.6 .35}
.count-main{font-weight:700;fill:var(--ink)}
.count-sub{fill:var(--ink-3);opacity:.75}
.count-on{fill:var(--ink-2);font-weight:700}
.sim{opacity:.55}
.simile-num.strong{fill:var(--ink);font-weight:800}
.beat-band{fill:var(--band)}
.grid-bar{fill:var(--rule)}
.grid-line{stroke:var(--rule)}
.grid-label{fill:var(--ink-2);font-weight:700}
.m-cym{fill:var(--cym)} .m-snr{fill:var(--snr)} .m-tom{fill:var(--tom)} .m-kik{fill:var(--kik)} .m-neu{fill:var(--neu)}
.m-cym-stroke{stroke:var(--cym)} .m-snr-stroke{stroke:var(--snr)} .m-tom-stroke{stroke:var(--tom)} .m-kik-stroke{stroke:var(--kik)} .m-neu-stroke{stroke:var(--neu)}
.accent-mark{stroke:var(--ink);stroke-width:.16}
.ghost-mark{fill-opacity:.25;stroke-width:.16}
.ghost-mark.m-cym{stroke:var(--cym)} .ghost-mark.m-snr{stroke:var(--snr)} .ghost-mark.m-tom{stroke:var(--tom)} .ghost-mark.m-kik{stroke:var(--kik)} .ghost-mark.m-neu{stroke:var(--neu)}
.open-mark{fill:var(--paper)!important;stroke-width:.22}
.open-mark.m-cym{stroke:var(--cym)} .open-mark.m-neu{stroke:var(--neu)}
.cut{stroke:var(--paper)}

/* system header lane: section box + tempo, in staff-space units so it zooms with the music */
.sys-head{display:flex;flex-wrap:wrap;align-items:center;gap:0 calc(var(--sp)*1.1px);
  padding-left:calc(var(--sp)*6.8px);margin-bottom:calc(var(--sp)*-0.2px);font-size:calc(var(--sp)*1.45px);line-height:1.25}
.secbox{font-family:var(--f-display);font-weight:800;font-stretch:80%;text-transform:uppercase;letter-spacing:.05em;
  border:calc(var(--sp)*0.16px) solid var(--ink);padding:.12em .45em .08em;font-size:1.12em}
.mark{font-family:var(--f-display);font-weight:800;background:var(--ink);color:var(--paper);padding:.12em .45em .08em;
  border:calc(var(--sp)*0.16px) solid var(--ink);margin-right:calc(var(--sp)*-1.1px);font-size:1.12em}
.secmeta{color:var(--ink-3);font-variant-numeric:tabular-nums;font-size:.9em}
.conf-chip{font-size:.78em;font-weight:700;border-radius:999px;padding:.1em .6em;border:1px solid currentColor}
.conf-chip.conf-medium{color:var(--warn-ink)} .conf-chip.conf-low{color:var(--low)}
.sys-head .tempo{display:inline-flex;align-items:baseline;gap:.25em;font-weight:700}
.tempo .tlabel{font-family:var(--f-body);margin-right:.35em}
.met{height:1.45em;width:auto;align-self:center;overflow:visible;display:inline-block}
.met use{fill:var(--ink)}

/* playback */
select{font:600 13px/1 var(--f-body);color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:7px;padding:8px 6px;min-height:34px}
.hl{fill:var(--hl);opacity:0;transition:opacity .08s}
.hl.on{opacity:1}
.ph{stroke:var(--kik);opacity:0}
body.playing .ph.on{opacity:.9}
.staff-svg{cursor:pointer}
.hl.start{opacity:1;fill:none;stroke:var(--kik);stroke-width:.14;stroke-dasharray:.5 .3}

/* notes */
.notes{margin-top:34px;padding-top:16px;border-top:2px solid var(--ink);display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px 40px}
.notes p,.notes li{max-width:68ch;color:var(--ink-2)}
.notes ul{padding-left:18px;margin:0}
.notes .conf{display:inline-block;font-size:12px;font-weight:700;border-radius:4px;padding:1px 6px;border:1px solid var(--rule)}
footer{margin-top:28px;font-size:12px;color:var(--ink-3)}

@media print{
  .bar,.road,.hint{display:none!important}
  .layout{display:none!important} .layout[data-per-line="4"]{display:block!important}
  .sys{width:100%!important}
  .sys > svg{width:min(100%, calc(var(--w) / var(--maxw) * 100%))!important}
  .sys-head{font-size:11pt!important;padding-left:5.6%!important}
  .key{break-after:auto}
  .mast{break-after:avoid}
  @page{size:auto;margin:14mm 12mm}
  .chart{overflow:visible}
  body{background:#fff}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

JS = r"""
(function(){
  var root=document.documentElement, body=document.body;
  var chart=document.getElementById('chart');
  var layouts=[].slice.call(document.querySelectorAll('.layout'));
  var widths={}; layouts.forEach(function(l){widths[l.dataset.perLine]=parseFloat(l.dataset.width)});
  var MIN_SP=7.5, MAX_SP=30, state={mode:'fit', sp:9};
  function store(k,v){try{localStorage.setItem('drumchart.'+k,JSON.stringify(v))}catch(e){}}
  function load(k,d){try{var v=localStorage.getItem('drumchart.'+k);return v===null?d:JSON.parse(v)}catch(e){return d}}
  function avail(){return Math.max(240, chart.clientWidth-2)}
  function choose(){
    var W=avail(), order=['4','2','1'].filter(function(k){return widths[k]});
    var pick=order[order.length-1], sp;
    if(state.mode==='fit'){
      for(var i=0;i<order.length;i++){var s=W/widths[order[i]]; if(s>=MIN_SP){pick=order[i];break}}
      sp=Math.min(MAX_SP, W/widths[pick]);
    }else{
      sp=state.sp;
      for(var j=0;j<order.length;j++){ if(widths[order[j]]*sp<=W){pick=order[j];break} }
    }
    root.style.setProperty('--sp', sp.toFixed(3));
    body.classList.toggle('fitmode', state.mode==='fit');
    layouts.forEach(function(l){l.classList.toggle('on', l.dataset.perLine===pick)});
    document.getElementById('zoomPct').textContent=Math.round(sp/9*100)+'%';
    document.getElementById('perLine').textContent=pick+(pick==='1'?' bar':' bars')+' / line';
    state.cur=sp;
  }
  function zoom(f){state.mode='manual'; state.sp=Math.max(5, Math.min(MAX_SP,(state.cur||9)*f)); store('zoom',state); choose(); setFit()}
  function setFit(){document.getElementById('fit').setAttribute('aria-pressed', state.mode==='fit'?'true':'false')}
  document.getElementById('zin').onclick=function(){zoom(1.15)};
  document.getElementById('zout').onclick=function(){zoom(1/1.15)};
  document.getElementById('fit').onclick=function(){state.mode='fit'; store('zoom',state); choose(); setFit()};
  function toggle(id,cls,key){var b=document.getElementById(id);
    function apply(on){b.setAttribute('aria-pressed',on?'true':'false'); body.classList.toggle(cls,!on)}
    var on=load(key,true); apply(on);
    b.onclick=function(){on=b.getAttribute('aria-pressed')!=='true'; apply(on); store(key,on)}}
  toggle('tGrid','no-grid','grid'); toggle('tCounts','no-counts','counts');
  var fb=document.getElementById('tFocus');
  fb.onclick=function(){var on=fb.getAttribute('aria-pressed')!=='true'; fb.setAttribute('aria-pressed',on?'true':'false'); body.classList.toggle('focus',on); choose()};
  document.addEventListener('keydown',function(e){
    if(e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if(e.key==='+'||e.key==='='){zoom(1.15);e.preventDefault()}
    else if(e.key==='-'||e.key==='_'){zoom(1/1.15);e.preventDefault()}
    else if(e.key==='0'){state.mode='fit';choose();setFit()}
    else if(e.key==='g'){document.getElementById('tGrid').click()}
    else if(e.key==='c'){document.getElementById('tCounts').click()}
    else if(e.key==='f'){fb.click()}
  });
  chart.addEventListener('wheel',function(e){ if(e.ctrlKey||e.metaKey){ e.preventDefault(); zoom(e.deltaY<0?1.08:1/1.08)} },{passive:false});
  var saved=load('zoom',null); if(saved&&saved.mode){state=saved}
  setFit(); choose();
  var t; window.addEventListener('resize',function(){clearTimeout(t); t=setTimeout(choose,80)});
  if(window.ResizeObserver){ new ResizeObserver(function(){clearTimeout(t); t=setTimeout(choose,60)}).observe(chart) }
  // road-map jumps land on the visible layout's copy of the section
  [].forEach.call(document.querySelectorAll('.road a'),function(a){a.addEventListener('click',function(e){
    var on=document.querySelector('.layout.on'); if(!on) return;
    var tgt=on.querySelector('[data-sec="'+a.dataset.sec+'"]'); if(tgt){e.preventDefault(); tgt.scrollIntoView({behavior:'smooth',block:'start'})}
  })});
})();
"""

JS_PLAYER = r"""
(function(){
  var data=JSON.parse(document.getElementById('chart-data').textContent);
  var bars=data.bars, body=document.body, ctx=null, master=null;
  var playBtn=document.getElementById('pPlay'), rateSel=document.getElementById('pRate');
  var st={playing:false, start:0, t0:0, songStart:0, ev:[], ei:0, rate:1, timer:null, raf:null, cur:-1, loopEnd:null, loopStart:null};
  function tog(id){var b=document.getElementById(id); b.onclick=function(){b.setAttribute('aria-pressed', b.getAttribute('aria-pressed')==='true'?'false':'true'); if(st.playing&&id==='pLoop'){setLoop()}}; return b}
  var loopB=tog('pLoop'), clickB=tog('pClick'), countB=tog('pCount');
  function on(b){return b.getAttribute('aria-pressed')==='true'}
  function init(){
    if(ctx) return;
    var AC=window.AudioContext||window.webkitAudioContext; ctx=new AC();
    master=ctx.createGain(); master.gain.value=0.8;
    var comp=ctx.createDynamicsCompressor(); master.connect(comp); comp.connect(ctx.destination);
  }
  // Real recorded drums (Hydrogen GMRockKit, GPL-3.0): base64 MP3s in #kit-data, decoded on first play.
  var KIT=null, BUF={}, kitReady=null, ring={};
  function loadKit(){
    if(kitReady) return kitReady;
    var el=document.getElementById('kit-data'); KIT=el?JSON.parse(el.textContent):{s:{},pan:{}};
    var jobs=[];
    Object.keys(KIT.s).forEach(function(id){BUF[id]={}; Object.keys(KIT.s[id]).forEach(function(l){
      var bin=atob(KIT.s[id][l]), u=new Uint8Array(bin.length); for(var i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i);
      jobs.push(new Promise(function(res){try{var p=ctx.decodeAudioData(u.buffer,function(b){BUF[id][l]=b;res()},function(){res()});
        if(p&&p.catch) p.catch(function(){res()})}catch(e){res()}}))})});
    kitReady=Promise.all(jobs); return kitReady;
  }
  var NOM={soft:0.3,medium:0.7,hard:1.0};
  function sampleFor(inst,art){
    switch(inst){
      case 'BD': return ['kick',1]; case 'B2': return ['kick',0.96];
      case 'SN': return art==='c'?['stick',1]:(art==='r'||art==='R')?['rimshot',1]:['snare',1];
      case 'T1': return ['tom1',1]; case 'T2': return ['tom2',1]; case 'T3': return ['tom2',0.89];
      case 'FT': return ['floor',1]; case 'F2': return ['floor',0.89];
      case 'HH': return (art==='o'||art==='O')?['hat-open',1,'hh']:art==='h'?['hat-half',1,'hh']:['hat',1,'hh'];
      case 'HF': return art==='o'?['hat-half',1,'hh']:['hat-pedal',1,'hh'];
      case 'RD': return (art==='b'||art==='B')?['bell',1]:['ride',1];
      case 'R2': return (art==='b'||art==='B')?['bell',0.94]:['ride2',1];
      case 'CR': return ['crash',1]; case 'C2': return ['crash',1.12]; case 'SP': return ['splash',1];
      case 'CH': return ['crash',0.8]; case 'CB': return ['cowbell',1]; case 'TB': return ['hat',1.6];
    }
    return null;
  }
  function voice(inst,art,t,v){
    var m=sampleFor(inst,art); if(!m||!BUF[m[0]]) return;
    var layer=v>=0.9?'hard':v>=0.45?'medium':'soft', b=BUF[m[0]][layer]||BUF[m[0]].medium||BUF[m[0]].hard||BUF[m[0]].soft;
    if(!b) return;
    var src=ctx.createBufferSource(); src.buffer=b; src.playbackRate.value=m[1];
    var g=ctx.createGain(); g.gain.value=Math.min(1.4,Math.max(0.15,v/NOM[layer]))*0.9;
    var out=g; src.connect(g);
    if(ctx.createStereoPanner&&KIT.pan[m[0]]){var pn=ctx.createStereoPanner(); pn.pan.value=KIT.pan[m[0]]*0.6; g.connect(pn); out=pn}
    out.connect(master);
    if(m[2]){var prev=ring[m[2]]; if(prev&&prev.end>t){prev.g.gain.setTargetAtTime(0,t,0.012)} ring[m[2]]={g:g,end:t+b.duration/m[1]}}
    src.start(t);
    if(art==='k'){g.gain.setTargetAtTime(0,t+0.11,0.03); src.stop(t+0.4)}
  }
  function play(inst,art,t,slot){
    var v=({X:1.0,O:1.0,F:1.0,B:1.0,R:1.0,g:0.26})[art]||0.72;
    if(art==='f'||art==='F') voice(inst,'x',t-0.028,0.35);
    if(art==='d'){voice(inst,'x',t-0.06,0.3); voice(inst,'x',t-0.03,0.3)}
    if(art==='z'){for(var k=0;k<6;k++) voice(inst,'x',t+k*slot/6,0.28); return}
    voice(inst,art,t,v);
  }
  function tone(t,f0,peak,dec){var o=ctx.createOscillator(); o.type='square'; o.frequency.setValueAtTime(f0,t);
    var g=ctx.createGain(); g.gain.setValueAtTime(0.0001,t); g.gain.exponentialRampToValueAtTime(peak,t+0.002); g.gain.exponentialRampToValueAtTime(0.0001,t+0.002+dec);
    o.connect(g); g.connect(master); o.start(t); o.stop(t+dec+0.05)}
  function click(t,strong){tone(t,strong?1900:1350,0.25,0.03)}
  function barIndexAt(sec){var lo=0,hi=bars.length-1; while(lo<hi){var m=(lo+hi+1)>>1; if(bars[m].t<=sec+1e-6) lo=m; else hi=m-1} return lo}
  function buildEvents(fromIdx,toIdx){
    var ev=[];
    for(var i=fromIdx;i<=toIdx;i++){var b=bars[i];
      b.h.forEach(function(h){ev.push([b.t+h[0],0,h[1],h[2],h[3]])});
      if(on(clickB)){var acc=b.t; for(var r=0;r<b.r;r++){b.bt.forEach(function(d,j){ev.push([acc,1,j===0]); acc+=d})}}
    }
    ev.sort(function(a,b){return a[0]-b[0]}); return ev;
  }
  function setLoop(){
    if(!on(loopB)){st.loopStart=st.loopEnd=null; return}
    var cur=bars[Math.max(0,st.cur)], s=cur.s, a=bars.findIndex(function(b){return b.s===s}), z=a;
    while(z+1<bars.length&&bars[z+1].s===s) z++;
    st.loopStart=a; st.loopEnd=z;
  }
  function start(fromIdx){
    if(rec.on&&rec.el){ if(ctx) clearInterval(st.timer); startRec(fromIdx); return }
    if(rec.el) rec.el.pause();
    init(); if(ctx.state==='suspended') ctx.resume();
    if(!kitReady||!st.kitLoaded){playBtn.innerHTML='Loading drums…'; playBtn.disabled=true;
      loadKit().then(function(){st.kitLoaded=true; playBtn.disabled=false; start(fromIdx)}); return}
    st.rate=parseFloat(rateSel.value)||1; st.start=fromIdx; st.cur=fromIdx; setLoop(); st.cur=-1;
    var last=st.loopEnd!=null?st.loopEnd:bars.length-1;
    st.ev=buildEvents(fromIdx,last); st.ei=0; st.songStart=bars[fromIdx].t;
    var lead=0.12;
    if(on(countB)){var b=bars[fromIdx], acc=0; b.bt.forEach(function(d,j){click(ctx.currentTime+lead+acc/st.rate,j===0); acc+=d}); lead+=acc/st.rate}
    st.t0=ctx.currentTime+lead; st.playing=true; body.classList.add('playing');
    playBtn.setAttribute('aria-pressed','true'); playBtn.innerHTML='&#10074;&#10074; Pause';
    clearInterval(st.timer); st.timer=setInterval(schedule,25); cancelAnimationFrame(st.raf); st.raf=requestAnimationFrame(frame);
  }
  function stop(){
    if(rec.el) rec.el.pause();
    st.playing=false; clearInterval(st.timer); cancelAnimationFrame(st.raf); body.classList.remove('playing');
    playBtn.setAttribute('aria-pressed','false'); playBtn.innerHTML='&#9654; Play';
  }
  function schedule(){
    var horizon=ctx.currentTime+0.15;
    while(st.ei<st.ev.length){var e=st.ev[st.ei], at=st.t0+(e[0]-st.songStart)/st.rate; if(at>horizon) break;
      if(at>=ctx.currentTime-0.02){ if(e[1]===0) play(e[2],e[3],at,e[4]/st.rate); else click(at,e[2]) } st.ei++}
  }
  function hlFor(n){var lay=document.querySelector('.layout.on'); return lay?lay.querySelectorAll('.hl[data-b="'+n+'"]'):[]}
  function frame(){
    if(!st.playing) return;
    var pos=(rec.on&&rec.el)?toChart(rec.el.currentTime):st.songStart+(ctx.currentTime-st.t0)*st.rate;
    if(rec.on&&rec.el&&rec.el.ended){stop(); return}
    var endIdx=st.loopEnd!=null?st.loopEnd:bars.length-1, end=bars[endIdx].t+bars[endIdx].d;
    if(pos>=end-0.005){ if(st.loopEnd!=null){start(st.loopStart); return} stop(); return }
    var i=Math.max(st.start,barIndexAt(Math.max(pos,bars[st.start].t)));
    var b=bars[i];
    if(i!==st.cur||!document.querySelector('.layout.on .hl.on')){
      document.querySelectorAll('.hl.on').forEach(function(x){x.classList.remove('on')});
      document.querySelectorAll('.ph.on').forEach(function(x){x.classList.remove('on')});
      st.cur=i; var hs=hlFor(b.n);
      hs.forEach(function(x){x.classList.add('on')});
      if(hs[0]){var r=hs[0].getBoundingClientRect(); if(r.top<80||r.bottom>window.innerHeight-40) hs[0].closest('.sys').scrollIntoView({behavior:'smooth',block:'center'})}
    }
    var h=hlFor(b.n)[0];
    if(h){var bx=h.getAttribute('data-bx').split(',').map(Number), off=Math.max(0,pos-b.t), x;
      if(b.r>1){x=bx[0]+(bx[bx.length-1]-bx[0])*Math.min(1,off/b.d)}
      else{var acc=0,j=0; while(j<b.bt.length-1&&off>acc+b.bt[j]){acc+=b.bt[j];j++} var fr=Math.min(1,(off-acc)/b.bt[j]); x=bx[j]+(bx[j+1]-bx[j])*fr}
      var ph=h.ownerSVGElement.querySelector('.ph'); ph.setAttribute('x1',x); ph.setAttribute('x2',x); ph.classList.add('on')}
    st.raf=requestAnimationFrame(frame);
  }
  // ---- play along with the user's own recording (never uploaded: an object URL in this tab) ----
  var rec={el:null,on:false,off:0}, secs=data.sections;
  (function(){var prev=null; secs.forEach(function(s){var b=bars.find(function(x){return x.n===s.first}); s.c=b?b.t:0;
      if(s.at==null) s.a=prev?prev.a+(s.c-prev.c):s.c; else s.a=s.at; prev=s});})();
  try{rec.off=parseFloat(localStorage.getItem('drumchart.recoff.'+document.title))||0}catch(e){}
  function toAudio(t){var s=secs[0]; secs.forEach(function(x){if(x.c<=t+1e-6) s=x}); return Math.max(0,s.a+(t-s.c)+rec.off)}
  function toChart(a){a-=rec.off; var s=secs[0]; secs.forEach(function(x){if(x.a<=a+1e-6) s=x}); return s.c+(a-s.a)}
  var recFile=document.getElementById('recFile'), recUse=document.getElementById('recUse');
  var recE=document.getElementById('recEarlier'), recL=document.getElementById('recLater');
  function nudge(d){rec.off=Math.round((rec.off+d)*10)/10; try{localStorage.setItem('drumchart.recoff.'+document.title,rec.off)}catch(e){}
    recUse.title='Recording offset '+(rec.off>=0?'+':'')+rec.off.toFixed(1)+' s'; if(st.playing&&rec.on) start(Math.max(st.start,st.cur))}
  recE.onclick=function(){nudge(-0.1)}; recL.onclick=function(){nudge(0.1)};
  recFile.onchange=function(){var f=recFile.files&&recFile.files[0]; if(!f) return;
    if(rec.el){rec.el.pause(); URL.revokeObjectURL(rec.el.src)}
    rec.el=new Audio(URL.createObjectURL(f)); rec.el.preservesPitch=true; rec.el.mozPreservesPitch=true;
    recUse.disabled=recE.disabled=recL.disabled=false; rec.on=true; recUse.setAttribute('aria-pressed','true');
    recUse.textContent='Recording: '+(f.name.length>18?f.name.slice(0,17)+'…':f.name); if(st.playing) start(Math.max(st.start,st.cur))};
  recUse.onclick=function(){if(!rec.el) return; rec.on=!rec.on; recUse.setAttribute('aria-pressed',rec.on?'true':'false');
    if(st.playing) start(Math.max(st.start,st.cur))};
  function startRec(fromIdx){
    st.rate=parseFloat(rateSel.value)||1; st.start=fromIdx; st.cur=fromIdx; setLoop(); st.cur=-1;
    rec.el.playbackRate=st.rate; rec.el.currentTime=toAudio(bars[fromIdx].t);
    var p=rec.el.play(); if(p&&p.catch) p.catch(function(){stop()});
    st.playing=true; body.classList.add('playing'); playBtn.setAttribute('aria-pressed','true'); playBtn.innerHTML='&#10074;&#10074; Pause';
    clearInterval(st.timer); cancelAnimationFrame(st.raf); st.raf=requestAnimationFrame(frame);
  }
  window.drumchartState=function(){return {cur:st.cur,start:st.start,playing:st.playing,recording:!!(rec.on&&rec.el),
    t:rec.on&&rec.el?rec.el.currentTime:null}};  // read-only, for automated checks
  var startIdx=0;
  function markStart(i){startIdx=i; document.querySelectorAll('.hl.start').forEach(function(x){x.classList.remove('start')});
    if(i>0) document.querySelectorAll('.hl[data-b="'+bars[i].n+'"]').forEach(function(x){x.classList.add('start')})}
  playBtn.onclick=function(){ if(st.playing) stop(); else start(startIdx) };
  rateSel.onchange=function(){ if(rec.on&&rec.el){rec.el.playbackRate=parseFloat(rateSel.value)||1; return} if(st.playing) start(Math.max(st.start,st.cur)) };
  clickB.addEventListener('click',function(){ if(st.playing) start(Math.max(st.start,st.cur)) });
  document.addEventListener('keydown',function(e){ if(e.code==='Space'&&!/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName)){e.preventDefault(); playBtn.click()} });
  document.querySelectorAll('.staff-svg').forEach(function(svg){svg.addEventListener('click',function(ev){
    var pt=svg.createSVGPoint(); pt.x=ev.clientX; pt.y=ev.clientY; var p=pt.matrixTransform(svg.getScreenCTM().inverse());
    var hit=null; svg.querySelectorAll('.hl').forEach(function(r){var x=+r.getAttribute('x'), w=+r.getAttribute('width'); if(p.x>=x&&p.x<=x+w) hit=r});
    if(!hit) return; var n=+hit.getAttribute('data-b'), i=bars.findIndex(function(b){return b.n===n}); if(i<0) return;
    markStart(i); if(st.playing) start(i)})});
})();
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,600..900'
         '&family=Atkinson+Hyperlegible:wght@400;700&family=EB+Garamond:ital,wght@1,500&display=swap">')


KIT_DIR = os.path.join(os.path.dirname(__file__), "assets", "kit")


def sample_for(inst: str, art: str) -> str | None:
    """Kit sample id that plays (inst, art); mirrors sampleFor() in JS_PLAYER."""
    if inst in ("BD", "B2"):
        return "kick"
    if inst == "SN":
        return "stick" if art == "c" else "rimshot" if art in "rR" else "snare"
    if inst in ("T1", "T2", "T3", "FT", "F2"):
        return {"T1": "tom1", "T2": "tom2", "T3": "tom2", "FT": "floor", "F2": "floor"}[inst]
    if inst == "HH":
        return "hat-open" if art in "oO" else "hat-half" if art == "h" else "hat"
    if inst == "HF":
        return "hat-half" if art == "o" else "hat-pedal"
    if inst in ("RD", "R2"):
        return "bell" if art in "bB" else ("ride" if inst == "RD" else "ride2")
    return {"CR": "crash", "C2": "crash", "CH": "crash", "SP": "splash", "CB": "cowbell", "TB": "hat"}.get(inst)


def kit_json(chart: Chart) -> str:
    """The real drum samples this chart needs (3 velocity layers each), base64 MP3."""
    import base64
    import json

    with open(os.path.join(KIT_DIR, "kit.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    need = set()
    for b in chart.bars:
        for h in b.hits:
            sid = sample_for(h.inst, h.art)
            if sid:
                need.add(sid)
            if h.art in "fFdz":  # grace notes and buzz strokes use the plain hit
                need.add(sample_for(h.inst, "x"))
    samples, pan = {}, {}
    for sid in sorted(need - {None}):
        entry = manifest["samples"][sid]
        pan[sid] = entry["pan"]
        samples[sid] = {}
        for layer, info in entry["layers"].items():
            with open(os.path.join(KIT_DIR, info["file"]), "rb") as fh:
                samples[sid][layer] = base64.b64encode(fh.read()).decode("ascii")
    return json.dumps({"s": samples, "pan": pan}, separators=(",", ":"))


def _at_seconds(at: str) -> float | None:
    """'1:02.5' -> 62.5 (None when the section has no usable timestamp)."""
    try:
        parts = [float(p) for p in (at or "").split(":")]
    except ValueError:
        return None
    if not parts or len(parts) > 3:
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return round(sec, 3)


def playback_json(chart: Chart) -> str:
    """Compact timing data for the in-page player: per bar start/duration, beat lengths and hits."""
    import json
    bars = []
    for si, sec in enumerate(chart.sections):
        for b in sec.bars:
            spw = 4 * 60.0 / b.tempo                     # seconds per whole note
            nb = b.rest_bars or 1
            beats = [round(float(D) * spw, 5) for D in b.meter.groups]
            hits = []
            if not b.rest_bars:
                for h in b.hits:
                    if h.inst == "ST":
                        continue
                    D = float(b.meter.groups[h.group])
                    hits.append([round(float(h.onset) * spw, 5), h.inst, h.art, round(D * spw / h.nslots, 5)])
            bars.append({"n": b.number, "t": round(b.start_time, 5), "d": round(sum(beats) * nb, 5),
                         "bt": beats, "r": nb, "s": si, "h": hits})
    secs = [{"name": s.name, "first": s.bars[0].number, "at": _at_seconds(s.at)} for s in chart.sections]
    return json.dumps({"bars": bars, "sections": secs}, separators=(",", ":"))


def source_script(source: str) -> str:
    """The chart's .drums text, embedded so a page can be turned back into an editable chart."""
    return '<script id="chart-source" type="text/plain">' + source.replace("</", "<\\/") + "</script>"


def extract_source(page_html: str) -> str | None:
    """Inverse of source_script(): the .drums text inside a rendered page, if any."""
    start = page_html.find('<script id="chart-source" type="text/plain">')
    if start < 0:
        return None
    start = page_html.index(">", start) + 1
    return page_html[start : page_html.index("</script>", start)].replace("<\\/", "</")


def render_page(chart: Chart, standalone: bool = True, source: str | None = None) -> str:
    """The chart page, engraved with the chart's staff key (header `notation:`, default drumkey)."""
    with staff_key(chart.meta.get("notation")):
        return _render_page(chart, standalone, source)


def _render_page(chart: Chart, standalone: bool, source: str | None) -> str:
    m = chart.meta
    title = m.get("title", "Untitled")
    # render every layout
    layout_html = []
    for L in LAYOUTS:
        systems = layout_chart(chart, L, CONTENT_W[L])
        rs: List[RenderedSystem] = [render_system(s, chart, i == len(systems) - 1, i == 0) for i, s in enumerate(systems)]
        nominal = CONTENT_W[L] + 7.0 + 0.6        # gutter + content + edge
        width = min(max(r.width for r in rs), nominal)
        parts = []
        for sl, r in zip(systems, rs):
            cls = "sys sec-start" if sl.section_start else "sys"
            ds = f' data-sec="{esc(r.section_id)}"' if sl.section_start else ""
            parts.append(f'<div class="{cls}"{ds} style="--w:{f(r.width)}">{r.head_html}{r.staff_svg}{r.counts_svg}{r.grid_svg}</div>')
        layout_html.append(f'<div class="layout{" on" if L == 4 else ""}" data-per-line="{L}" data-width="{f(width)}" style="--maxw:{f(width)}">'
                           + "".join(parts) + "</div>")

    # facts
    tempo = m.get("tempo", "")
    facts = []
    if tempo:
        bpm, unit, _ = tempo_parts(tempo)
        facts.append(("Tempo", tempo_html(bpm, unit, "")))
    facts.append(("Time", m.get("time", "4/4")))
    if m.get("feel"):
        facts.append(("Feel", m["feel"]))
    total = float(m.get("_total_seconds", "0") or 0)
    facts.append(("Length", m.get("length") or _fmt_time(total)))
    facts.append(("Bars", m.get("_total_bars", "")))
    facts_html = "".join(f"<div><dt>{esc(k)}</dt><dd>{v if k == 'Tempo' else esc(v)}</dd></div>" for k, v in facts)

    by = " · ".join(x for x in [m.get("artist"), m.get("album"), ("Drums: " + m["drummer"]) if m.get("drummer") else None] if x)

    # road map
    road = []
    for sec in chart.sections:
        nb = sum((b.rest_bars or 1) for b in sec.bars)
        mk = f'<span class="mk">{esc(sec.mark)}</span>' if sec.mark else ""
        q = '<span class="q" title="Lower confidence"></span>' if sec.confidence in ("medium", "low") else ""
        at = f" · {esc(sec.at)}" if sec.at else ""
        road.append(f'<li><a href="#{esc(section_id(sec))}" data-sec="{esc(section_id(sec))}">{mk}<span class="nm">{esc(sec.name)}</span>'
                    f'<span class="ct">{nb}{at}</span>{q}</a></li>')

    # key
    key_items = "".join(f"<li>{legend_svg(c, a)}<span>{esc(lab)}</span></li>" for c, a, lab in _legend_items(chart))
    arts_used = {(h.inst, h.art) for b in chart.bars for h in b.hits}
    a_used = {a for _, a in arts_used}
    want = {"hit": True, "accent": bool(a_used & set("XOFBR")), "ghost": "g" in a_used,
            "open": any(i in ("HH", "HF") and a in "oOh" for i, a in arts_used), "flam": bool(a_used & set("fF")),
            "cross": "c" in a_used, "bell": bool(a_used & set("bB")), "buzz": "z" in a_used}
    gk = "".join(f"<div>{grid_key_svg(k)}{esc(lab)}</div>" for k, lab in GRID_KEY if want.get(k))
    fams = ('<div class="fam"><span><i style="background:var(--cym)"></i>Cymbals &amp; hi-hat</span>'
            '<span><i style="background:var(--snr)"></i>Snare</span><span><i style="background:var(--tom)"></i>Toms</span>'
            '<span><i style="background:var(--kik)"></i>Kick</span><span><i style="background:var(--neu)"></i>Hi-hat foot / percussion</span></div>')

    # notes
    notes_parts = []
    conf_list = []
    for sec in chart.sections:
        # one entry per section: what to play, then how sure we are, then flagged bars
        parts = [esc(n) for n in sec.notes]
        if sec.confidence:
            parts.append(f'<span class="conf">{esc(sec.confidence)}</span> {esc(sec.confidence_note)}')
        bars = [f'<li>Bar {b.number} ({esc(sec.name)} bar {j + 1}) <span class="conf">{esc(b.confidence)}</span> '
                f'{esc(b.confidence_note)}</li>'
                for j, b in enumerate(sec.bars) if b.confidence and b.confidence_note]
        if parts or bars:
            sub = f"<ul>{''.join(bars)}</ul>" if bars else ""
            conf_list.append(f"<li><b>{esc(sec.name)}:</b> {' '.join(parts)}{sub}</li>")
    if conf_list:
        notes_parts.append("<div><h2>Transcription notes</h2><ul>" + "".join(conf_list) + "</ul></div>")
    about = []
    if m.get("notes"):
        about.append(f"<p>{esc(m['notes'])}</p>")
    if m.get("source") or m.get("sources"):
        about.append(f"<p><b>Sources:</b> {esc(m.get('source') or m.get('sources'))}</p>")
    if m.get("transcriber"):
        about.append(f"<p><b>Transcribed by:</b> {esc(m['transcriber'])}</p>")
    about.append('<p><b>Reading the chart:</b> bar numbers at the start of each line count from the top of the song; '
                 'numbers over repeat signs count bars within the section (bold on 4, 8, 12, 16). '
                 'Dashed outlines mark bars written from the best available evidence rather than a confident '
                 'hearing: amber for medium confidence, red for low. A dot in the road map marks a section with '
                 'lower confidence. Hover a dashed bar for the reason.</p>')
    notes_parts.append("<div><h2>About this chart</h2>" + "".join(about) + "</div>")

    body = f"""
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>{glyph_defs()}</defs></svg>
<div class="wrap">
  <header class="mast">
    <div>
      <div class="eyebrow">Drum chart</div>
      <h1>{esc(title)}</h1>
      <p class="byline">{esc(by)}</p>
    </div>
    <dl class="facts">{facts_html}</dl>
  </header>
  <nav class="bar" aria-label="Chart view controls">
    <div class="grp"><span class="grp-label">Zoom</span>
      <button id="zout" aria-label="Zoom out">−</button><span id="zoomPct" aria-live="polite">100%</span>
      <button id="zin" aria-label="Zoom in">+</button><button id="fit" aria-pressed="true">Fit width</button></div>
    <div class="grp" id="player"><span class="grp-label">Play</span>
      <button id="pPlay" aria-pressed="false" title="Play / pause (space)">&#9654; Play</button>
      <select id="pRate" aria-label="Playback speed">
        <option value="0.5">50%</option><option value="0.6">60%</option><option value="0.7">70%</option>
        <option value="0.8">80%</option><option value="0.9">90%</option><option value="1" selected>100%</option>
        <option value="1.1">110%</option></select>
      <button id="pLoop" aria-pressed="false" title="Loop the current section">Loop</button>
      <button id="pClick" aria-pressed="false" title="Metronome click">Click</button>
      <button id="pCount" aria-pressed="true" title="One bar count-in">Count-in</button></div>
    <div class="grp" id="recgrp"><span class="grp-label">Recording</span>
      <label class="tog" title="Play along with your own copy of the song (it stays on this device)">
        <input type="file" id="recFile" accept="audio/*,.mp3,.m4a,.wav,.flac,.ogg" hidden>Load song…</label>
      <button id="recUse" aria-pressed="false" disabled title="Play the recording (on) or the drum sounds (off)">Recording</button>
      <button id="recEarlier" disabled title="Nudge: the recording is late against the chart">−0.1 s</button>
      <button id="recLater" disabled title="Nudge: the recording is early against the chart">+0.1 s</button></div>
    <div class="grp"><span class="grp-label">Show</span>
      <button id="tCounts" aria-pressed="true">Counts</button><button id="tGrid" aria-pressed="true">Grid</button>
      <button id="tFocus" aria-pressed="false">Focus</button></div>
    <span class="spacer"></span><span class="hint" id="perLine">4 bars / line</span>
    <span class="hint">Keys: + − 0 · G grid · C counts · F focus</span>
  </nav>
  <section class="road" aria-label="Song road map"><h2>Road map</h2><ol>{''.join(road)}</ol></section>
  <section class="key" aria-label="Drum key"><div><h2>Drum key</h2><ul>{key_items}</ul></div>
    <div><h2>Grid key</h2><div class="gk">{gk}</div>{fams}</div></section>
  <main class="chart" id="chart">{''.join(layout_html)}</main>
  <section class="notes">{''.join(notes_parts)}</section>
  <footer>Engraved by drum-agent. Music symbols: Bravura © Steinberg Media Technologies, SIL Open Font License 1.1.
    Drum sounds: real recordings from Hydrogen's GMRockKit by Glen MacArthur and Sebastian Moors, GPL-3.0.</footer>
</div>
<script id="chart-data" type="application/json">{playback_json(chart)}</script>
<script id="kit-data" type="application/json">{kit_json(chart)}</script>
{source_script(source) if source else ""}
<script>{JS}</script>
<script>{JS_PLAYER}</script>
"""
    head = f"<title>{esc(title)} Drum Chart</title>{FONTS}<style>{CSS}</style>"
    if not standalone:
        return head + body
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            + head + "</head><body>" + body + "</body></html>")
