"""PyInstaller entry point (absolute imports; ``__main__.py`` uses relative ones)."""
import sys

from warpzip.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
