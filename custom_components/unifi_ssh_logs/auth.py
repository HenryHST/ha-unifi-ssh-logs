"""SSH auth resolution for UniFi SSH Logs (key and/or password)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Host token in known_hosts first column (exact match, not substring).
_HOST_TOKEN_RE = re.compile(r"^\[?([^\]:\s]+)\]?(?::\d+)?$")


class AuthConfigError(ValueError):
    """Raised when neither a usable key nor a password is configured."""


@dataclass(frozen=True)
class SshAuth:
    """Resolved credentials for asyncssh.connect."""

    key_path: str | None
    password: str | None
    private_key: str | None = None

    def to_connect_kwargs(self, asyncssh_mod: Any | None = None) -> dict[str, Any]:
        """Build asyncssh keyword args (without host/username/known_hosts)."""
        kwargs: dict[str, Any] = {}
        if self.private_key:
            mod = asyncssh_mod
            if mod is None:
                import asyncssh as mod
            kwargs["client_keys"] = [mod.import_private_key(self.private_key)]
        elif self.key_path:
            kwargs["client_keys"] = [self.key_path]
        if self.password:
            kwargs["password"] = self.password
        return kwargs


def generate_key() -> tuple[str, str]:
    """Return a new (private OpenSSH, public OpenSSH) ed25519 key pair."""
    import asyncssh

    key = asyncssh.generate_private_key(
        "ssh-ed25519", comment="home-assistant-unifi-ssh-logs"
    )
    return key.export_private_key().decode(), key.export_public_key().decode().strip()


def public_key_of(private_key: str) -> str:
    """Return the OpenSSH public key line for a private key string."""
    import asyncssh

    return (
        asyncssh.import_private_key(private_key)
        .export_public_key()
        .decode()
        .strip()
    )


def host_in_known_hosts(known_hosts_path: Path, host: str) -> bool:
    """Return True if ``host`` is listed as its own token in known_hosts."""
    if not known_hosts_path.is_file():
        return False
    try:
        text = known_hosts_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    target = host.strip().lower()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names = stripped.split()[0]
        for token in names.split(","):
            match = _HOST_TOKEN_RE.match(token.strip())
            if match and match.group(1).lower() == target:
                return True
    return False


def resolve_known_hosts_arg(known_hosts_path: str | Path, host: str) -> str | None:
    """
    Path for asyncssh known_hosts, or None to accept a new host key.

    Matches OpenSSH ``StrictHostKeyChecking=accept-new``: trust existing
    entries; if the host is missing, skip verification for this connect.
    """
    path = Path(known_hosts_path)
    if host_in_known_hosts(path, host):
        return str(path)
    if path.is_file():
        _LOGGER.warning(
            "Host %s not in %s; accepting new host key for this connection",
            host,
            path,
        )
    else:
        _LOGGER.warning(
            "known_hosts file %s missing; accepting host key for %s",
            path,
            host,
        )
    return None


def resolve_ssh_auth(
    key_path: str | None,
    password: str | None,
    *,
    private_key: str | None = None,
    key_must_exist: bool = True,
) -> SshAuth:
    """
    Resolve SSH auth: inline private_key, then key file, then password.

    Raises AuthConfigError if no usable credentials.
    """
    inline = (private_key or "").strip() or None
    if inline and not inline.endswith("\n"):
        inline = inline + "\n"

    key = (key_path or "").strip() or None
    pwd = password if password else None
    if pwd is not None:
        pwd = str(pwd)
        if pwd == "":
            pwd = None

    if inline:
        return SshAuth(key_path=None, password=pwd, private_key=inline)

    usable_key: str | None = None
    if key:
        if not key_must_exist or Path(key).is_file():
            usable_key = key
        elif pwd is None:
            raise AuthConfigError("key_missing")

    if usable_key is None and pwd is None:
        raise AuthConfigError("auth_missing")

    return SshAuth(key_path=usable_key, password=pwd, private_key=None)


def incremental_new_lines(
    cursors: dict[str, str],
    cursor_key: str,
    lines: list[str],
    *,
    first_run_cap: int = 50,
) -> list[str]:
    """
    Return only lines after the last seen fingerprint; update cursors in place.

    On first sight of cursor_key, return at most ``first_run_cap`` trailing lines
    to avoid an alert storm.
    """
    if not lines:
        return []
    last = cursors.get(cursor_key)
    if last is None:
        cursors[cursor_key] = lines[-1]
        return lines[-first_run_cap:]
    try:
        idx = len(lines) - 1 - lines[::-1].index(last)
        new = lines[idx + 1 :]
    except ValueError:
        new = lines
    cursors[cursor_key] = lines[-1]
    return new
