"""Log directory retention / rotation helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Only rotate / list files we create (timestamped fetches + support bundles).
LOG_FILE_GLOBS = (
    "messages-*.log",
    "journal-unifi-*.txt",
    "unifi-server-*.log",
    "unifi-core-*.log",
    "support-*.tar.gz",
)
_GLOB_PATTERNS = LOG_FILE_GLOBS


def rotate_log_dir(
    out_dir: Path,
    *,
    max_files: int = 40,
    max_age_days: int = 7,
) -> list[str]:
    """
    Delete old log artifacts by age and keep at most ``max_files`` newest.

    Returns paths that were removed.
    """
    if not out_dir.is_dir():
        return []

    files: list[Path] = []
    for pattern in _GLOB_PATTERNS:
        files.extend(out_dir.glob(pattern))
    # unique by resolve
    unique = {p.resolve(): p for p in files if p.is_file()}
    paths = list(unique.values())
    removed: list[str] = []

    now = time.time()
    max_age_sec = max(0, int(max_age_days)) * 86400
    if max_age_sec > 0:
        for path in list(paths):
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age > max_age_sec:
                try:
                    path.unlink()
                    removed.append(str(path))
                    paths.remove(path)
                except OSError as err:
                    _LOGGER.warning("Failed to delete old log %s: %s", path, err)

    if max_files > 0 and len(paths) > max_files:
        paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        for path in paths[max_files:]:
            try:
                path.unlink()
                removed.append(str(path))
            except OSError as err:
                _LOGGER.warning("Failed to delete excess log %s: %s", path, err)

    if removed:
        _LOGGER.info("Log retention removed %d file(s)", len(removed))
    return removed
