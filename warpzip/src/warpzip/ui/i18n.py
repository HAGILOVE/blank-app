"""Tiny translation helper: tr("한국어", "English")."""
from __future__ import annotations

import locale

_lang = "ko"


def system_language() -> str:
    try:
        loc = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").lower()
    except Exception:  # noqa: BLE001
        loc = ""
    if not loc:
        try:
            from PySide6.QtCore import QLocale
            loc = QLocale.system().name().lower()
        except Exception:  # noqa: BLE001
            loc = ""
    return "ko" if loc.startswith("ko") or "korea" in loc else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = system_language() if lang in ("auto", "", None) else lang


def language() -> str:
    return _lang


def tr(ko: str, en: str) -> str:
    return ko if _lang == "ko" else en
