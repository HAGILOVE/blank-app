"""Tree + table model that lets users browse an archive like a folder."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from ..core.entry import Entry
from ..core.fsutil import human_size
from . import icons
from .i18n import tr


class Node:
    __slots__ = ("name", "path", "is_dir", "entry", "size", "packed", "mtime", "children", "encrypted", "count")

    def __init__(self, name: str, path: str, is_dir: bool, entry: Optional[Entry] = None) -> None:
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.entry = entry
        self.size = entry.size if entry and not is_dir else 0
        self.packed = entry.packed if entry and not is_dir else 0
        self.mtime: Optional[datetime] = entry.mtime if entry else None
        self.encrypted = bool(entry and entry.encrypted)
        self.children: Dict[str, "Node"] = {}
        self.count = 0


class ArchiveTree:
    def __init__(self, entries: List[Entry]) -> None:
        self.entries = entries
        self.root = Node("", "", True)
        self.by_path: Dict[str, Node] = {"": self.root}
        for e in entries:
            self._add(e)
        self._sum(self.root)

    def _add(self, e: Entry) -> None:
        parts = e.path.split("/")
        cur = self.root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            path = "/".join(parts[: i + 1])
            node = cur.children.get(part)
            if node is None:
                node = Node(part, path, (not last) or e.is_dir, e if last else None)
                cur.children[part] = node
                self.by_path[path] = node
            elif last:
                node.entry = e
                node.is_dir = e.is_dir
                if not e.is_dir:
                    node.size, node.packed = e.size, e.packed
                node.mtime = e.mtime
                node.encrypted = e.encrypted
            cur = node

    def _sum(self, n: Node) -> None:
        if not n.is_dir:
            n.count = 1
            return
        size = packed = count = 0
        for c in n.children.values():
            self._sum(c)
            size += c.size
            packed += max(c.packed, 0)
            count += c.count
            if c.mtime and (n.mtime is None or c.mtime > n.mtime) and n is self.root:
                pass
        n.size, n.packed, n.count = size, packed, count

    def entries_for(self, nodes: List[Node]) -> List[Entry]:
        """All real entries below / at the given nodes (deduplicated, archive order)."""
        prefixes = [(n.path, n.is_dir) for n in nodes]
        out: Dict[int, Entry] = {}
        for e in self.entries:
            for p, is_dir in prefixes:
                if e.path == p or (is_dir and (p == "" or e.path.startswith(p + "/"))):
                    out[e.index] = e
                    break
        return sorted(out.values(), key=lambda x: x.index)


COLS = 6


class ArchiveModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tree: Optional[ArchiveTree] = None
        self.cwd = ""
        self.rows: List[Node] = []
        self.query = ""

    # -- structure ------------------------------------------------------------------
    def set_tree(self, tree: Optional[ArchiveTree]) -> None:
        self.beginResetModel()
        self.tree = tree
        self.cwd = ""
        self.query = ""
        self._rebuild()
        self.endResetModel()

    def cd(self, path: str) -> None:
        self.beginResetModel()
        self.cwd = path
        self.query = ""
        self._rebuild()
        self.endResetModel()

    def search(self, text: str) -> None:
        self.beginResetModel()
        self.query = text.strip().lower()
        self._rebuild()
        self.endResetModel()

    def _rebuild(self) -> None:
        if not self.tree:
            self.rows = []
            return
        if self.query:
            base = self.tree.by_path.get(self.cwd, self.tree.root)
            out: List[Node] = []
            stack = list(base.children.values())
            while stack:
                n = stack.pop()
                if self.query in n.name.lower():
                    out.append(n)
                if n.is_dir:
                    stack.extend(n.children.values())
            self.rows = out
        else:
            base = self.tree.by_path.get(self.cwd, self.tree.root)
            self.rows = list(base.children.values())

    def node(self, row: int) -> Node:
        return self.rows[row]

    # -- Qt API -------------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else COLS

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return [tr("이름", "Name"), tr("크기", "Size"), tr("압축 크기", "Packed"), tr("압축률", "Ratio"),
                    tr("수정한 날짜", "Modified"), tr("종류", "Type")][section]
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole and section in (1, 2, 3):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        n = self.rows[index.row()]
        c = index.column()
        if role == Qt.DisplayRole:
            if c == 0:
                return n.path if self.query else n.name
            if c == 1:
                return human_size(n.size) if (not n.is_dir or n.size) else ""
            if c == 2:
                return human_size(n.packed) if n.packed > 0 else ""
            if c == 3:
                if n.packed > 0 and n.size > 0:
                    return f"{max(0.0, 1 - n.packed / n.size) * 100:.0f}%"
                return ""
            if c == 4:
                return n.mtime.strftime("%Y-%m-%d %H:%M") if n.mtime else ""
            if c == 5:
                if n.is_dir:
                    return tr("폴더", "Folder")
                return n.name.rsplit(".", 1)[-1].upper() if "." in n.name else tr("파일", "File")
        elif role == Qt.DecorationRole and c == 0:
            return icons.file_icon(n.name, n.is_dir)
        elif role == Qt.TextAlignmentRole and c in (1, 2, 3):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        elif role == Qt.ToolTipRole and c == 0:
            return n.path
        elif role == Qt.UserRole:
            return n
        return None


class ArchiveProxy(QSortFilterProxyModel):
    def lessThan(self, left, right) -> bool:
        m: ArchiveModel = self.sourceModel()
        a, b = m.node(left.row()), m.node(right.row())
        asc = self.sortOrder() == Qt.AscendingOrder
        if a.is_dir != b.is_dir:
            return a.is_dir == asc            # folders stay on top in both directions
        c = left.column()
        if c == 1:
            ka, kb = a.size, b.size
        elif c == 2:
            ka, kb = a.packed, b.packed
        elif c == 3:
            ka = 1 - a.packed / a.size if a.size and a.packed > 0 else -1
            kb = 1 - b.packed / b.size if b.size and b.packed > 0 else -1
        elif c == 4:
            ka, kb = a.mtime or datetime.min, b.mtime or datetime.min
        elif c == 5:
            ka, kb = a.name.rsplit(".", 1)[-1].lower(), b.name.rsplit(".", 1)[-1].lower()
        else:
            ka, kb = a.name.casefold(), b.name.casefold()
        return ka < kb
