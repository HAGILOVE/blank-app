"""Entry point: ``python -m warpzip`` / WarpZip.exe / wz.exe."""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    from . import cli

    if argv and argv[0] in ("--install-shell", "--uninstall-shell", "--register-assoc"):
        return _shell(argv)

    if argv and (argv[0] in cli.COMMANDS or argv[0] in ("--version", "-h", "--help")):
        return cli.run(argv)
    from .app import run_gui

    return run_gui(argv)


def _shell(argv) -> int:
    """Used by the installer: no GUI, no console window."""
    from .shell import windows_integration as wi

    lang = argv[1] if len(argv) > 1 else "ko"
    if argv[0] == "--install-shell":
        wi.install_context_menu(lang)
    elif argv[0] == "--uninstall-shell":
        wi.uninstall_context_menu()
        wi.unregister_associations()
    else:
        wi.register_associations([".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".001"], lang)
    return 0


if __name__ == "__main__":
    sys.exit(main())
