"""Exception hierarchy used across the engine."""
from __future__ import annotations


class WarpError(Exception):
    """Base class of all engine errors."""


class Cancelled(WarpError):
    """The user cancelled the running job."""


class PasswordRequired(WarpError):
    """The archive (or part of it) is encrypted and no password was given."""


class WrongPassword(WarpError):
    """The supplied password does not decrypt the archive."""


class UnsupportedFormat(WarpError):
    """The file is not an archive WARPZIP can handle."""


class CorruptArchive(WarpError):
    """The archive is damaged or truncated."""


class UnsafePath(WarpError):
    """An archive member tried to escape the extraction folder."""


class DiskSpaceError(WarpError):
    """Not enough free space on the destination drive."""


class ToolMissing(WarpError):
    """An optional external tool (7-Zip) is required but was not found."""
