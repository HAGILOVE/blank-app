"""Cute UI icon set (48x48 grid, pastel fill + ink outline).

The ink colour is a placeholder (#3B2A6B) that the app swaps for a theme colour
at load time, so the same SVGs work in light and dark mode.
"""
from __future__ import annotations

from mascot import (BLUE, CREAM, INK, LAV, MINT, ORANGE, PINK, SPARK, STAR, VIOLET, YELLOW)

RED = "#FF6B81"
GREEN = "#5BD98E"
D = "#3B2A6A"  # detail colour: stays dark in every theme (INK is swapped)
SW = 2.8  # outline width

S = f'stroke="{INK}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"'


def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">{body}</svg>'


def face(cx: float, cy: float, k: float = 1.0, smile: bool = True) -> str:
    out = (f'<ellipse cx="{cx-5*k}" cy="{cy}" rx="{1.7*k}" ry="{2.1*k}" fill="{D}"/>'
           f'<ellipse cx="{cx+5*k}" cy="{cy}" rx="{1.7*k}" ry="{2.1*k}" fill="{D}"/>')
    if smile:
        out += f'<path d="M{cx-2.4*k},{cy+3.4*k} q{2.4*k},{2.6*k} {4.8*k},0" fill="none" stroke="{D}" stroke-width="{2*k}" stroke-linecap="round"/>'
    out += (f'<ellipse cx="{cx-8.6*k}" cy="{cy+3*k}" rx="{2.2*k}" ry="{1.4*k}" fill="{PINK}" opacity=".8"/>'
            f'<ellipse cx="{cx+8.6*k}" cy="{cy+3*k}" rx="{2.2*k}" ry="{1.4*k}" fill="{PINK}" opacity=".8"/>')
    return out


def badge(cx: float, cy: float, color: str, glyph: str) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="9" fill="{color}" {S}/>{glyph}'


PLUS = lambda cx, cy: f'<path d="M{cx-4},{cy} h8 M{cx},{cy-4} v8" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>'


def parcel(y_shift: float = 0) -> str:
    return (f'<rect x="7" y="19" width="34" height="22" rx="6" fill="{CREAM}" {S}/>'
            f'<rect x="5" y="11" width="38" height="11" rx="5" fill="{LAV}" {S}/>'
)


def folder(fill: str = YELLOW) -> str:
    return (f'<path d="M5,15 q0,-4 4,-4 h9 l4,4.5 h16 q4,0 4,4 v17 q0,4 -4,4 h-29 q-4,0 -4,-4z" fill="{fill}" {S}/>'
            f'<path d="M5,21 h38" stroke="{INK}" stroke-width="2.4" opacity=".35"/>')


def page(fill: str, glyph: str = "", fold: str = "#fff") -> str:
    return (f'<path d="M11,6 h18 l9,9 v24 q0,4 -4,4 h-23 q-4,0 -4,-4 v-29 q0,-4 4,-4z" fill="{fill}" {S}/>'
            f'<path d="M29,6 v6 q0,3 3,3 h6" fill="{fold}" {S}/>' + glyph)


ICONS: dict[str, str] = {}


def icon(name: str):
    def deco(fn):
        ICONS[name] = svg(fn())
        return fn
    return deco


@icon("add")  # compress
def _():
    return parcel() + face(24, 31, .9) + badge(37, 36, MINT, PLUS(37, 36))


@icon("extract")
def _():
    return (f'<path d="M7,26 l-3,-11 l15,4z" fill="{LAV}" {S}/><path d="M41,26 l3,-11 l-15,4z" fill="{LAV}" {S}/>'
            f'<rect x="7" y="24" width="34" height="17" rx="6" fill="{CREAM}" {S}/>'
            f'<path d="M24,26 v-21 M17,12 l7,-8 l7,8" fill="none" stroke="{VIOLET}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M24,26 v-21 M17,12 l7,-8 l7,8" fill="none" stroke="{INK}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0"/>'
            + face(24, 33, .85))


@icon("extract_here")
def _():
    return (f'<rect x="6" y="6" width="36" height="36" rx="10" fill="{MINT}" {S}/>'
            f'<path d="M24,13 v18 M16,24 l8,8 l8,-8" fill="none" stroke="#fff" stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M14,37 h20" stroke="#fff" stroke-width="4" stroke-linecap="round"/>')


@icon("open")
def _():
    return (f'<path d="M5,15 q0,-4 4,-4 h9 l4,4.5 h14 q4,0 4,4 v3" fill="{ORANGE}" {S}/>'
            f'<path d="M3,40 l5,-17 q1,-3 4,-3 h31 q3,0 2,3 l-5,17 q-1,3 -4,3 h-29 q-3,0 -4,-3z" fill="{YELLOW}" {S}/>'
            f'<circle cx="21" cy="30" r="1.7" fill="{INK}"/><circle cx="31" cy="30" r="1.7" fill="{INK}"/>'
            f'<path d="M23,34 q3,3 6,0" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>')


@icon("test")
def _():
    return (f'<path d="M24,5 l16,6 v12 q0,13 -16,20 q-16,-7 -16,-20 v-12z" fill="{LAV}" {S}/>'
            f'<path d="M16,24 l6,6 l11,-12" fill="none" stroke="{GREEN}" stroke-width="5.2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M16,24 l6,6 l11,-12" fill="none" stroke="{INK}" stroke-width="1" opacity="0"/>')


@icon("info")
def _():
    return (f'<path d="M24,5 q18,0 18,16 q0,16 -18,16 h-3 l-9,7 v-8 q-6,-4 -6,-15 q0,-16 18,-16z" fill="{BLUE}" {S}/>'
            f'<circle cx="24" cy="14.5" r="2.7" fill="#fff"/><path d="M24,21 v10" stroke="#fff" stroke-width="4.4" stroke-linecap="round"/>')


@icon("delete")
def _():
    return (f'<path d="M10,14 h28 l-2.5,25 q-.4,4 -4,4 h-15 q-3.6,0 -4,-4z" fill="{PINK}" {S}/>'
            f'<path d="M7,14 h34" {S}/><path d="M18,14 v-4 q0,-3 3,-3 h6 q3,0 3,3 v4" fill="none" {S}/>'
            + "")


@icon("add_file")
def _():
    return page(CREAM) + badge(35, 36, MINT, PLUS(35, 36)) + f'<path d="M16,22 h12 M16,28 h8" stroke="{INK}" stroke-width="2.6" stroke-linecap="round" opacity=".5"/>'


@icon("add_folder")
def _():
    return folder() + badge(35, 35, MINT, PLUS(35, 35))


@icon("folder")
def _():
    return folder()


ICONS["folder_open"] = ICONS["open"]


@icon("settings")
def _():
    return (f'<path d="M24,4 l4,3 l5,-1 l2,5 l5,2 l-1,5 l3,4 l-3,4 l1,5 l-5,2 l-2,5 l-5,-1 l-4,3 l-4,-3 l-5,1 l-2,-5 l-5,-2 l1,-5 l-3,-4 l3,-4 l-1,-5 l5,-2 l2,-5 l5,1z" fill="{LAV}" {S}/>'
            f'<circle cx="24" cy="24" r="8.5" fill="{CREAM}" {S}/>')


@icon("lock")
def _():
    return (f'<path d="M14,22 v-6 q0,-10 10,-10 q10,0 10,10 v6" fill="none" stroke="{INK}" stroke-width="5.6" stroke-linecap="round"/>'
            f'<path d="M14,22 v-6 q0,-10 10,-10 q10,0 10,10 v6" fill="none" stroke="{LAV}" stroke-width="2.6" stroke-linecap="round"/>'
            f'<rect x="8" y="21" width="32" height="22" rx="7" fill="{YELLOW}" {S}/><circle cx="24" cy="31" r="3.2" fill="{D}"/>')


@icon("unlock")
def _():
    return (f'<path d="M14,22 v-6 q0,-10 10,-10 q10,0 10,6" fill="none" stroke="{INK}" stroke-width="5.6" stroke-linecap="round"/>'
            f'<path d="M14,22 v-6 q0,-10 10,-10 q10,0 10,6" fill="none" stroke="{LAV}" stroke-width="2.6" stroke-linecap="round"/>'
            f'<rect x="8" y="21" width="32" height="22" rx="7" fill="{MINT}" {S}/><circle cx="24" cy="31" r="3.2" fill="{D}"/>')


@icon("split")
def _():
    return (f'<path d="M5,16 q0,-5 5,-5 h11 l-3,10 l5,5 l-5,5 l3,10 h-11 q-5,0 -5,-5z" fill="{CREAM}" {S}/>'
            f'<path d="M43,16 q0,-5 -5,-5 h-11 l3,10 l-5,5 l5,5 l-3,10 h11 q5,0 5,-5z" fill="{LAV}" {S}/>'
            f'<path d="M24,5 v38" stroke="{PINK}" stroke-width="3" stroke-dasharray="1 5" stroke-linecap="round"/>')


@icon("hash")
def _():
    return (f'<rect x="5" y="5" width="38" height="38" rx="11" fill="{VIOLET}" {S}/>'
            f'<path d="M19,13 l-3,22 M31,13 l-3,22 M11,19 h26 M10,29 h26" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/>')


@icon("search")
def _():
    return (f'<circle cx="21" cy="21" r="13" fill="{LAV}" {S}/><path d="M31,31 l11,11" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
            f'<path d="M31,31 l11,11" stroke="{PINK}" stroke-width="2.6" stroke-linecap="round"/><path d="M14,17 q2,-5 7,-5" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>')


@icon("up")
def _():
    return (f'<path d="M24,6 l17,19 h-10 v15 q0,3 -3,3 h-8 q-3,0 -3,-3 v-15 h-10z" fill="{MINT}" {S}/>')


@icon("back")
def _():
    return (f'<path d="M6,24 l19,-17 v10 h14 q3,0 3,3 v8 q0,3 -3,3 h-14 v10z" fill="{LAV}" {S}/>')


@icon("home")
def _():
    return (f'<path d="M5,24 l19,-17 l19,17 h-5 v16 q0,3 -3,3 h-22 q-3,0 -3,-3 v-16z" fill="{CREAM}" {S}/>'
            f'<path d="M3,25 l21,-19 l21,19" fill="none" stroke="{PINK}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<rect x="19" y="28" width="10" height="15" rx="3" fill="{YELLOW}" {S}/>')


@icon("eye")
def _():
    return (f'<path d="M3,24 q21,-22 42,0 q-21,22 -42,0z" fill="#fff" {S}/><circle cx="24" cy="24" r="8" fill="{VIOLET}" {S}/>'
            f'<circle cx="21.5" cy="21.5" r="2.6" fill="#fff"/>')


@icon("rename")
def _():
    return (f'<path d="M8,40 l2,-9 l22,-22 l7,7 l-22,22z" fill="{YELLOW}" {S}/><path d="M32,9 l7,7" stroke="{INK}" stroke-width="2.8"/>'
            f'<path d="M32,9 l4,-4 q2,-2 4,0 l3,3 q2,2 0,4 l-4,4z" fill="{PINK}" {S}/><path d="M8,40 l2,-9 l7,7z" fill="{CREAM}" {S}/>')


@icon("convert")
def _():
    return (f'<path d="M7,17 h28 v-6 l9,10 l-9,10 v-6 h-28z" fill="{MINT}" {S}/>'
            f'<path d="M41,31 h-28 v-6 l-9,10 l9,10 v-6 h28z" fill="{PINK}" {S}/>')


@icon("copy")
def _():
    return (f'<rect x="14" y="14" width="27" height="29" rx="6" fill="{LAV}" {S}/><rect x="7" y="5" width="27" height="29" rx="6" fill="{CREAM}" {S}/>')


@icon("sun")
def _():
    rays = "".join(f'<path d="M24,4 v6" transform="rotate({a} 24 24)" stroke="{INK}" stroke-width="3.2" stroke-linecap="round"/>' for a in range(0, 360, 45))
    return rays + f'<circle cx="24" cy="24" r="11" fill="{YELLOW}" {S}/>'


@icon("moon")
def _():
    return (f'<path d="M30,5 q-18,2 -18,20 q0,17 19,17 q9,0 13,-6 q-20,6 -20,-16 q0,-10 6,-15z" fill="{YELLOW}" {S}/>'
            f'<g transform="translate(37,12) scale(.5)" fill="{MINT}" stroke="{INK}" stroke-width="3"><path d="{SPARK}"/></g>')


@icon("globe")
def _():
    return (f'<circle cx="24" cy="24" r="19" fill="{BLUE}" {S}/>'
            f'<path d="M13,14 q6,-3 9,2 q2,5 -3,7 q-5,1 -4,6 q-4,-2 -6,-7 q0,-5 4,-8z M30,28 q5,-2 8,2 q-2,6 -8,8 q-3,-4 0,-10z" fill="{GREEN}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>')


@icon("check")
def _():
    return f'<circle cx="24" cy="24" r="19" fill="{GREEN}" {S}/><path d="M14,25 l7,7 l13,-15" fill="none" stroke="#fff" stroke-width="5.4" stroke-linecap="round" stroke-linejoin="round"/>'


@icon("warning")
def _():
    return (f'<path d="M24,5 q3,0 4.6,3 l15,27 q2,6 -4,6 h-31.2 q-6,0 -4,-6 l15,-27 q1.6,-3 4.6,-3z" fill="{YELLOW}" {S}/>'
            f'<path d="M24,17 v11" stroke="{INK}" stroke-width="4.4" stroke-linecap="round"/><circle cx="24" cy="34" r="2.6" fill="{INK}"/>')


@icon("error")
def _():
    return f'<circle cx="24" cy="24" r="19" fill="{RED}" {S}/><path d="M16,16 l16,16 M32,16 l-16,16" stroke="#fff" stroke-width="5.4" stroke-linecap="round"/>'


@icon("star")
def _():
    return f'<g transform="translate(24,25) scale(1.4)" fill="{YELLOW}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"><path d="{STAR}"/></g>'


@icon("pin")
def _():
    return (f'<path d="M24,44 l-4,-12 h8z" fill="{INK}"/><path d="M14,8 h20 l-3,10 l5,10 h-24 l5,-10z" fill="{PINK}" {S}/>')


@icon("recent")
def _():
    return (f'<circle cx="24" cy="24" r="19" fill="{LAV}" {S}/><path d="M24,13 v12 l8,5" fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')


@icon("keyboard_pw")
def _():
    return (f'<circle cx="16" cy="24" r="10" fill="{YELLOW}" {S}/><circle cx="16" cy="24" r="3.4" fill="#fff" {S}/>'
            f'<path d="M26,24 h18 M38,24 v7 M32,24 v5" fill="none" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M26,24 h18 M38,24 v7 M32,24 v5" fill="none" stroke="{YELLOW}" stroke-width="2" stroke-linecap="round"/>')


@icon("bomb")
def _():
    return (f'<circle cx="21" cy="29" r="14" fill="{D}"/><path d="M28,17 q4,-6 9,-5" fill="none" {S}/>'
            f'<g transform="translate(40,10) scale(.5)" fill="{YELLOW}" stroke="{INK}" stroke-width="3"><path d="{SPARK}"/></g>'
            f'<circle cx="16" cy="24" r="3.2" fill="#fff" opacity=".7"/>')


# ----- file type glyphs -------------------------------------------------
G = lambda d, c="#fff": f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>'


@icon("f_file")
def _():
    return page(CREAM) + f'<path d="M15,24 h18 M15,30 h18 M15,36 h10" stroke="{INK}" stroke-width="2.4" stroke-linecap="round" opacity=".35"/>'


@icon("f_text")
def _():
    return page("#EEF3FF") + f'<path d="M15,23 h18 M15,29 h18 M15,35 h11" stroke="{BLUE}" stroke-width="3" stroke-linecap="round"/>'


@icon("f_image")
def _():
    return (page("#D9FBF3") + f'<circle cx="31" cy="25" r="3" fill="{YELLOW}" {S}/>'
            f'<path d="M12,40 l8,-10 l5,6 l4,-4 l8,8z" fill="{MINT}" stroke="{INK}" stroke-width="2.2" stroke-linejoin="round"/>')


@icon("f_audio")
def _():
    return (page("#FFE3EE") + f'<path d="M20,35 v-12 l12,-3 v12" fill="none" {S}/>'
            f'<circle cx="18" cy="35" r="3.6" fill="{PINK}" {S}/><circle cx="30" cy="32" r="3.6" fill="{PINK}" {S}/>')


@icon("f_video")
def _():
    return page("#EDE7FF") + f'<path d="M19,22 l12,7 l-12,7z" fill="{VIOLET}" {S}/>'


@icon("f_code")
def _():
    return page("#E8FFF0") + G("M20,24 l-5,5 l5,5", D) + G("M28,24 l5,5 l-5,5", D)


@icon("f_archive")
def _():
    return (page(LAV) + f'<path d="M24,6 v6 M24,17 v3 M24,25 v3" stroke="{INK}" stroke-width="3" stroke-dasharray="2 3" stroke-linecap="round"/>'
            f'<rect x="19" y="30" width="10" height="9" rx="3" fill="{PINK}" {S}/>')


@icon("f_exe")
def _():
    return (page("#FFF1D6") + f'<rect x="14" y="21" width="20" height="15" rx="3" fill="#fff" {S}/><path d="M14,26 h20" {S}/>'
            f'<circle cx="18" cy="23.6" r=".9" fill="{INK}"/>')


@icon("f_doc")
def _():
    return page("#DDEBFF") + f'<path d="M15,23 h18 M15,29 h18 M15,35 h11" stroke="{BLUE}" stroke-width="3" stroke-linecap="round"/>' + f'<rect x="8" y="30" width="16" height="10" rx="3" fill="{BLUE}" {S}/><path d="M12,35 h8" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'


@icon("f_sheet")
def _():
    return (page("#E0FBEA") + f'<rect x="14" y="22" width="20" height="15" rx="2" fill="#fff" {S}/>'
            f'<path d="M14,27 h20 M14,32 h20 M22,22 v15" stroke="{GREEN}" stroke-width="2.2"/>')


@icon("f_pdf")
def _():
    return page("#FFE1E1") + f'<rect x="9" y="29" width="24" height="12" rx="4" fill="{RED}" {S}/><path d="M13,35 h2 q2,0 2,-2 M21,32 v6 M26,32 h4 M26,35 h3" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>'


@icon("f_font")
def _():
    return page("#FFF6D6") + G("M16,37 l8,-16 l8,16 M19,31 h10", D)


@icon("f_disk")
def _():
    return (page("#E3E7F5") + f'<circle cx="24" cy="30" r="8" fill="#fff" {S}/><circle cx="24" cy="30" r="2.4" fill="{D}"/>')


# extension -> icon mapping used by the UI
EXT_ICON = {
    "f_text": "txt md log ini cfg conf json xml yaml yml csv tsv rtf nfo srt",
    "f_image": "png jpg jpeg gif bmp webp svg ico tif tiff heic avif psd",
    "f_audio": "mp3 wav flac ogg m4a aac wma opus mid",
    "f_video": "mp4 mkv avi mov wmv webm flv m4v ts",
    "f_code": "py js ts jsx tsx html htm css c h cpp hpp cs java go rs rb php sh bat ps1 sql lua kt swift",
    "f_archive": "zip 7z rar tar gz tgz bz2 xz zst iso cab wim arj lzh 001",
    "f_exe": "exe msi dll sys com scr apk app",
    "f_doc": "doc docx odt hwp hwpx pages",
    "f_sheet": "xls xlsx ods numbers",
    "f_pdf": "pdf",
    "f_font": "ttf otf woff woff2",
    "f_disk": "img vhd vhdx dmg bin",
    "f_video_": "",
}
