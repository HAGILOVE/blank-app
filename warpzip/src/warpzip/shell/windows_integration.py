"""Explorer right-click menu and file associations (per-user, no admin rights).

The registry layout is produced by :func:`context_menu_plan` / :func:`association_plan`
as plain data so it can be unit-tested on any OS; ``winreg`` is only touched in
the apply/remove helpers.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Tuple

from ..core.formats import ASSOCIABLE

IS_WINDOWS = sys.platform == "win32"
PROG_ID = "WarpZip.Archive"
VERB = "WarpZip"
ARCHIVE_EXTS = [e for e in ASSOCIABLE if e != ".001"] + [".001"]

# (key path below HKCU, value name, value)
RegItem = Tuple[str, str, str]


def launcher() -> str:
    """Command prefix that starts WARPZIP (frozen exe or ``python -m warpzip``)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m warpzip'


def icon_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    return str(Path(__file__).resolve().parents[1] / "assets" / "app.ico")


def context_menu_plan(lang: str = "ko", cmd: str | None = None, icon: str | None = None) -> List[RegItem]:
    cmd = cmd or launcher()
    icon = icon or icon_path()
    ko = lang == "ko"
    t_compress = "WARPZIP으로 압축하기…" if ko else "Compress with WARPZIP…"
    t_zip = "WARPZIP: '이름.zip'으로 바로 압축" if ko else "WARPZIP: Quick ZIP"
    t_7z = "WARPZIP: '이름.7z'으로 바로 압축" if ko else "WARPZIP: Quick 7Z"
    t_ask = "WARPZIP으로 풀기…" if ko else "Extract with WARPZIP…"
    t_here = "WARPZIP: 여기에 풀기" if ko else "WARPZIP: Extract here"
    t_folder = "WARPZIP: 폴더를 만들어 풀기" if ko else "WARPZIP: Extract to folder"
    items: List[RegItem] = []

    def verb(base: str, name: str, label: str, args: str, pos: str = "") -> None:
        k = f"Software\\Classes\\{base}\\shell\\{name}"
        items.append((k, "", label))
        items.append((k, "Icon", icon))
        if pos:
            items.append((k, "Position", pos))
        items.append((k + "\\command", "", f'{cmd} {args} "%1"'))

    for base in ("*", "Directory"):
        verb(base, f"{VERB}.Compress", t_compress, "--compress")
        verb(base, f"{VERB}.QuickZip", t_zip, "--quick-zip")
        verb(base, f"{VERB}.Quick7z", t_7z, "--quick-7z")
    for ext in ARCHIVE_EXTS:
        base = f"SystemFileAssociations\\{ext}"
        verb(base, f"{VERB}.Extract", t_ask, "--extract")
        verb(base, f"{VERB}.Here", t_here, "--extract-here")
        verb(base, f"{VERB}.Folder", t_folder, "--extract-folder")
    return items


def association_plan(exts: Iterable[str], cmd: str | None = None, lang: str = "ko") -> List[RegItem]:
    cmd = cmd or launcher()
    arch_icon = (f'"{sys.executable}",1' if getattr(sys, "frozen", False)
                 else str(Path(__file__).resolve().parents[1] / "assets" / "archive.ico"))
    items: List[RegItem] = [
        (f"Software\\Classes\\{PROG_ID}", "", "WARPZIP Archive" if lang != "ko" else "WARPZIP 압축 파일"),
        (f"Software\\Classes\\{PROG_ID}\\DefaultIcon", "", arch_icon),
        (f"Software\\Classes\\{PROG_ID}\\shell\\open", "", "Open with WARPZIP" if lang != "ko" else "WARPZIP으로 열기"),
        (f"Software\\Classes\\{PROG_ID}\\shell\\open\\command", "", f'{cmd} "%1"'),
        ("Software\\WarpZip\\Capabilities", "ApplicationName", "WARPZIP"),
        ("Software\\WarpZip\\Capabilities", "ApplicationDescription", "WARPZIP archive manager"),
        ("Software\\RegisteredApplications", "WarpZip", "Software\\WarpZip\\Capabilities"),
    ]
    for ext in exts:
        items.append((f"Software\\Classes\\{ext}\\OpenWithProgids", PROG_ID, ""))
        items.append(("Software\\WarpZip\\Capabilities\\FileAssociations", ext, PROG_ID))
    return items


def _winreg():
    import winreg
    return winreg


def _apply(items: List[RegItem]) -> None:
    wr = _winreg()
    for key, name, value in items:
        with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, key, 0, wr.KEY_SET_VALUE) as k:
            wr.SetValueEx(k, name, 0, wr.REG_SZ, value)


def _delete_tree(root: str) -> None:
    wr = _winreg()
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, root, 0, wr.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = wr.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root + "\\" + sub)
        wr.DeleteKey(wr.HKEY_CURRENT_USER, root)
    except FileNotFoundError:
        pass


def _notify() -> None:
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:  # noqa: BLE001
        pass


def context_menu_installed() -> bool:
    if not IS_WINDOWS:
        return False
    wr = _winreg()
    try:
        wr.CloseKey(wr.OpenKey(wr.HKEY_CURRENT_USER, f"Software\\Classes\\*\\shell\\{VERB}.Compress"))
        return True
    except OSError:
        return False


def install_context_menu(lang: str = "ko") -> bool:
    if not IS_WINDOWS:
        return False
    uninstall_context_menu()
    _apply(context_menu_plan(lang))
    _notify()
    return True


def uninstall_context_menu() -> bool:
    if not IS_WINDOWS:
        return False
    for base in ("*", "Directory"):
        for v in ("Compress", "QuickZip", "Quick7z"):
            _delete_tree(f"Software\\Classes\\{base}\\shell\\{VERB}.{v}")
    for ext in ARCHIVE_EXTS:
        for v in ("Extract", "Here", "Folder"):
            _delete_tree(f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\{VERB}.{v}")
    _notify()
    return True


def register_associations(exts: Iterable[str], lang: str = "ko") -> bool:
    if not IS_WINDOWS:
        return False
    _apply(association_plan(list(exts), lang=lang))
    _notify()
    return True


def unregister_associations() -> bool:
    if not IS_WINDOWS:
        return False
    wr = _winreg()
    for ext in ARCHIVE_EXTS:
        try:
            with wr.OpenKey(wr.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}\\OpenWithProgids", 0, wr.KEY_SET_VALUE) as k:
                wr.DeleteValue(k, PROG_ID)
        except OSError:
            pass
    _delete_tree(f"Software\\Classes\\{PROG_ID}")
    _delete_tree("Software\\WarpZip")
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, "Software\\RegisteredApplications", 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, "WarpZip")
    except OSError:
        pass
    _notify()
    return True


def open_default_apps_settings() -> None:
    if IS_WINDOWS:
        import os
        os.startfile("ms-settings:defaultapps")  # type: ignore[attr-defined]
