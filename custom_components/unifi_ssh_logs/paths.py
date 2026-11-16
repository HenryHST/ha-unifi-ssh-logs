"""Path allowlist helpers — keep SSH/log paths under HA config dir."""

from __future__ import annotations

from pathlib import Path


class PathConfigError(ValueError):
    """Raised when a configured path escapes the config directory."""


def resolve_under_config(
    path: str | Path | None,
    config_dir: str | Path,
    *,
    allow_empty: bool = False,
) -> Path | None:
    """
    Resolve ``path`` and require it to stay under ``config_dir``.

    Relative paths are joined under ``config_dir``. Raises PathConfigError
    on ``..`` escapes or absolute paths outside the config root.
    """
    if path is None or str(path).strip() == "":
        if allow_empty:
            return None
        raise PathConfigError("path_outside_config")

    root = Path(config_dir).expanduser().resolve()
    candidate = Path(str(path).strip()).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as err:
        raise PathConfigError("path_outside_config") from err
    return resolved


def require_under_config(
    path: str | Path,
    config_dir: str | Path,
) -> Path:
    """Like resolve_under_config but never returns None."""
    result = resolve_under_config(path, config_dir, allow_empty=False)
    assert result is not None
    return result
