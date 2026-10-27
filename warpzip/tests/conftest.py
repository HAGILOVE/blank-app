import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false;qt.qpa.fonts=false")


@pytest.fixture
def sample(tmp_path):
    src = tmp_path / "data"
    (src / "sub" / "deep").mkdir(parents=True)
    (src / "emptydir").mkdir()
    (src / "a.txt").write_text("hello 안녕 " * 2000, encoding="utf-8")
    (src / "sub" / "b.bin").write_bytes(os.urandom(200_000))
    (src / "sub" / "deep" / "c.txt").write_text("deep file")
    (src / "empty.txt").write_text("")
    (src / "pic.jpg").write_bytes(b"\xff\xd8" + b"x" * 5000)
    return src
