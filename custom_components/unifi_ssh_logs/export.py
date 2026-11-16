"""List and export UniFi SSH log artifacts under out_dir."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .retention import LOG_FILE_GLOBS


def list_log_files(out_dir: Path) -> list[dict[str, Any]]:
    """Return metadata for integration log artifacts in ``out_dir``."""
    if not out_dir.is_dir():
        return []
    files: list[Path] = []
    for pattern in LOG_FILE_GLOBS:
        files.extend(out_dir.glob(pattern))
    unique = {p.resolve(): p for p in files if p.is_file()}
    rows: list[dict[str, Any]] = []
    for path in sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = path.stat()
        except OSError:
            continue
        rows.append(
            {
                "name": path.name,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "text": _is_text_log(path.name),
            }
        )
    return rows


def resolve_log_file(out_dir: Path, name: str) -> Path:
    """
    Resolve ``name`` under ``out_dir``; raise ValueError if unsafe/missing.

    ``name`` must be a bare filename matching our log globs.
    """
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("invalid_name")
    out_resolved = out_dir.resolve()
    candidate = (out_dir / name).resolve()
    try:
        candidate.relative_to(out_resolved)
    except ValueError as err:
        raise ValueError("path_outside_out_dir") from err
    if not candidate.is_file():
        raise ValueError("not_found")
    allowed = {row["name"] for row in list_log_files(out_dir)}
    if candidate.name not in allowed:
        raise ValueError("not_allowed")
    return candidate


def _is_text_log(name: str) -> bool:
    lower = name.lower()
    return lower.endswith((".log", ".txt")) and not lower.endswith(".tar.gz")


def lines_to_csv(text: str) -> str:
    """Convert newline-delimited log text to CSV with line_no,line columns."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["line_no", "line"])
    for idx, line in enumerate(text.splitlines(), start=1):
        writer.writerow([idx, line])
    return buf.getvalue()


def export_file_bytes(path: Path, fmt: str) -> tuple[bytes, str, str]:
    """
    Return (body, content_type, download_filename) for txt/csv/binary.

    ``fmt`` is ``txt`` or ``csv``. Support archives are always returned as gzip.
    """
    name = path.name
    if name.lower().endswith(".tar.gz"):
        data = path.read_bytes()
        return data, "application/gzip", name

    text = path.read_text(encoding="utf-8", errors="replace")
    fmt_norm = (fmt or "txt").lower()
    # Do not embed charset= in content_type — aiohttp web.Response rejects it.
    if fmt_norm == "csv":
        body = lines_to_csv(text).encode("utf-8")
        return body, "text/csv", f"{path.stem}.csv"
    body = text.encode("utf-8")
    return body, "text/plain", name
