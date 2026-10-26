"""Warpy (워피) - the WARPZIP mascot: a round marshmallow with a zipper-pull on its head.

Deliberately simple: flat colours, one bold outline, dot eyes, tiny smile.
"""
from __future__ import annotations

INK = "#3B2A6B"
VIOLET = "#7C5CFF"
VIOLET_D = "#5B3FD6"
LAV = "#E4DBFF"
PINK = "#FF8FB8"
MINT = "#5EEAD4"
YELLOW = "#FFD166"
CREAM = "#FFF8F0"
ORANGE = "#FFA45B"
BLUE = "#6CB6FF"

STAR = "M0,-15 L4.4,-5 L15,-4.5 L6.8,2.5 L9.5,13 L0,7.2 L-9.5,13 L-6.8,2.5 L-15,-4.5 L-4.4,-5 Z"
SPARK = "M0,-10 C1.2,-3 3,-1.2 10,0 C3,1.2 1.2,3 0,10 C-1.2,3 -3,1.2 -10,0 C-3,-1.2 -1.2,-3 0,-10 Z"

MOODS = ("idle", "happy", "work", "sad", "sleep")


def _eyes(mood: str) -> str:
    L, R = (98, 124), (158, 124)
    if mood in ("happy", "done"):
        arc = lambda x, y: f'<path d="M{x-11},{y+5} Q{x},{y-10} {x+11},{y+5}" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>'
        return arc(*L) + arc(*R)
    if mood == "sleep":
        ln = lambda x, y: f'<path d="M{x-11},{y} Q{x},{y+8} {x+11},{y}" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
        return ln(*L) + ln(*R)
    if mood == "work":
        return (f'<path d="M{L[0]-9},{L[1]-9} L{L[0]+8},{L[1]} L{L[0]-9},{L[1]+9}" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="M{R[0]+9},{R[1]-9} L{R[0]-8},{R[1]} L{R[0]+9},{R[1]+9}" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>')
    dot = lambda x, y: f'<circle cx="{x}" cy="{y}" r="11.5" fill="{INK}"/><circle cx="{x-3.5}" cy="{y-4}" r="3.6" fill="#fff"/>'
    out = dot(*L) + dot(*R)
    if mood == "sad":
        out += f'<path d="M{L[0]+12},{L[1]+14} q5,9 0,13 q-5,-4 0,-13z" fill="{BLUE}"/>'
    return out


def _mouth(mood: str) -> str:
    if mood == "sad":
        return f'<path d="M116,162 Q128,150 140,162" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
    if mood in ("happy", "done"):
        return f'<path d="M110,146 Q128,172 146,146 Z" fill="{INK}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>' \
               f'<path d="M118,156 Q128,164 138,156" fill="none" stroke="{PINK}" stroke-width="5" stroke-linecap="round"/>'
    if mood == "sleep":
        return f'<path d="M118,152 Q128,158 138,152" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
    return f'<path d="M114,148 Q128,164 142,148" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'


def mascot_body(mood: str = "idle", uid: str = "") -> str:
    """Drawing inside a 256x256 box (no <svg> wrapper)."""
    extra = ""
    if mood == "sleep":
        extra = (f'<text x="190" y="72" font-family="Segoe UI,Arial" font-weight="800" font-size="34" fill="{VIOLET}">z</text>'
                 f'<text x="212" y="44" font-family="Segoe UI,Arial" font-weight="800" font-size="24" fill="{MINT}">z</text>')
    elif mood == "work":
        extra = f'<path d="M20,110 h22 M12,134 h22 M24,158 h16" stroke="{MINT}" stroke-width="8" stroke-linecap="round"/>'
    elif mood in ("happy", "done"):
        extra = (f'<g transform="translate(42,82)" fill="{YELLOW}"><path d="{SPARK}"/></g>'
                 f'<g transform="translate(218,110) scale(.7)" fill="{MINT}"><path d="{SPARK}"/></g>'
                 f'<g transform="translate(212,200) scale(.8)" fill="{PINK}"><path d="{SPARK}"/></g>')
    return f"""
  <ellipse cx="128" cy="226" rx="62" ry="9" fill="{VIOLET}" opacity=".16"/>
  <rect x="116" y="26" width="24" height="44" rx="12" fill="{PINK}" stroke="{INK}" stroke-width="8"/>
  <circle cx="128" cy="40" r="4.4" fill="#fff"/>
  <rect x="44" y="56" width="168" height="162" rx="76" fill="{CREAM}" stroke="{INK}" stroke-width="8"/>
  <ellipse cx="76" cy="152" rx="14" ry="9" fill="{PINK}" opacity=".75"/>
  <ellipse cx="180" cy="152" rx="14" ry="9" fill="{PINK}" opacity=".75"/>
  {_eyes(mood)}
  {_mouth(mood)}
  {extra}"""


def mascot_svg(mood: str = "idle") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
            f'{mascot_body(mood)}</svg>')


def app_icon_svg(simple: bool = False) -> str:
    """Flat violet tile with Warpy (same drawing at every size, bold enough for 16px)."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <rect x="6" y="6" width="244" height="244" rx="62" fill="{VIOLET}"/>
  <g transform="translate(128,134) scale(.86) translate(-128,-128)">{mascot_body("idle").replace('<ellipse cx="128" cy="226" rx="62" ry="9" fill="#7C5CFF" opacity=".16"/>', '')}</g>
</svg>"""
