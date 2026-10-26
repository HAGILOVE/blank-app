"""Generate every WARPZIP asset: SVG icons, mascot poses, .ico files, installer art.

Run:  python tools/make_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from icons import EXT_ICON, ICONS  # noqa: E402
from mascot import MOODS, INK, PINK, LAV, VIOLET, app_icon_svg, mascot_svg  # noqa: E402
from render import ensure_app, render  # noqa: E402

ROOT = HERE.parent
ASSETS = ROOT / "src" / "warpzip" / "assets"
PACK = ROOT / "packaging"

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def assoc_icon_svg() -> str:
    """Icon for archive files in Explorer: violet page with a zipper pull and a smile."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
<path d="M52,16 h110 l56,56 v146 q0,22 -22,22 h-144 q-22,0 -22,-22 v-180 q0,-22 22,-22z" fill="{VIOLET}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
<path d="M162,16 v36 q0,20 20,20 h36" fill="{LAV}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>
<rect x="112" y="22" width="32" height="64" rx="16" fill="{PINK}" stroke="{INK}" stroke-width="9"/>
<circle cx="128" cy="42" r="6" fill="#fff"/>
<circle cx="94" cy="156" r="13" fill="{INK}"/><circle cx="162" cy="156" r="13" fill="{INK}"/>
<circle cx="90" cy="151" r="4.5" fill="#fff"/><circle cx="158" cy="151" r="4.5" fill="#fff"/>
<path d="M112,182 q16,16 32,0" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
<ellipse cx="72" cy="182" rx="13" ry="8" fill="{PINK}" opacity=".85"/><ellipse cx="184" cy="182" rx="13" ry="8" fill="{PINK}" opacity=".85"/>
</svg>"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_ico(path: Path, svg_big: str, svg_small: str | None = None) -> None:
    from PIL import Image
    import io
    frames = []
    for s in ICO_SIZES:
        src = svg_small if (svg_small and s <= 32) else svg_big
        img = render(src, s)
        from PySide6.QtCore import QBuffer, QIODevice
        qb = QBuffer()
        qb.open(QIODevice.WriteOnly)
        img.save(qb, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(qb.data()))).convert("RGBA"))
    big = frames[-1]
    big.save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1])


def make_installer_art() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    ensure_app()
    # wizard image 164x314
    w, h = 164, 314
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#9B7BFF"))
    g.setColorAt(0.55, QColor("#7C5CFF"))
    g.setColorAt(1, QColor("#FF8FB8"))
    p.fillRect(0, 0, w, h, g)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawImage(QRectF(6, 70, 152, 152), render(mascot_svg("happy"), 304))
    p.setPen(QColor("white"))
    f = QFont("Arial", 17)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 18, w, 40), Qt.AlignHCenter | Qt.AlignVCenter, "WARPZIP")
    f2 = QFont("Arial", 8)
    p.setFont(f2)
    p.drawText(QRectF(0, 252, w, 30), Qt.AlignHCenter | Qt.AlignVCenter, "Zip at warp speed")
    p.end()
    PACK.mkdir(exist_ok=True)
    img.save(str(PACK / "wizard.bmp"), "BMP")
    # small 55x58
    small = QImage(55, 58, QImage.Format_RGB32)
    small.fill(QColor("#FFFFFF"))
    p = QPainter(small)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawImage(QRectF(0, 1, 55, 55), render(app_icon_svg(True), 110))
    p.end()
    small.save(str(PACK / "wizard_small.bmp"), "BMP")


def main() -> None:
    ensure_app()
    for name, text in ICONS.items():
        write(ASSETS / "icons" / f"{name}.svg", text)
    for mood in MOODS + ("done",):
        write(ASSETS / "mascot" / f"warpy_{mood}.svg", mascot_svg(mood))
    write(ASSETS / "app_icon.svg", app_icon_svg())
    write(ASSETS / "app_icon_small.svg", app_icon_svg(True))
    write(ASSETS / "archive_icon.svg", assoc_icon_svg())
    make_ico(ASSETS / "app.ico", app_icon_svg(), app_icon_svg(True))
    make_ico(ASSETS / "archive.ico", assoc_icon_svg())
    render(app_icon_svg(), 512).save(str(ASSETS / "app_icon_512.png"))
    render(mascot_svg("idle"), 512).save(str(ASSETS / "mascot" / "warpy_idle_512.png"))
    # extension -> icon table (consumed by ui/icons.py)
    table = {ext: icon for icon, exts in EXT_ICON.items() for ext in exts.split()}
    import json
    write(ASSETS / "ext_icons.json", json.dumps(table, indent=1, ensure_ascii=False))
    make_installer_art()
    print(f"icons={len(ICONS)} mascot={len(MOODS) + 1} -> {ASSETS}")


if __name__ == "__main__":
    main()
