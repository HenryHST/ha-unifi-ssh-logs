"""Redact secrets from log samples and error strings before HA exposure."""

from __future__ import annotations

import re

_KV_SECRET = re.compile(
    r"(?i)\b(password|passwd|pwd|passphrase|secret|token|api[_-]?key|"
    r"authorization|bearer|cookie|set-cookie)\b\s*([=:])\s*\S+"
)
_HEADER_SECRET = re.compile(r"(?i)\b(authorization|cookie)\s*:\s*\S+")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+=/]+")
_PEM_KEY = re.compile(
    r"-----BEGIN[^-]+PRIVATE KEY-----.*?-----END[^-]+PRIVATE KEY-----",
    re.DOTALL | re.IGNORECASE,
)
_ERROR_USER_AT = re.compile(r"(?i)\b([\w.-]+@)[\w.-]+")


def redact_text(text: str, *, max_len: int = 240) -> str:
    """Redact secret-like substrings and truncate for entity/event exposure."""
    if not text:
        return ""
    out = _PEM_KEY.sub("-----BEGIN PRIVATE KEY-----**REDACTED**-----END PRIVATE KEY-----", text)
    out = _BEARER.sub("Bearer **REDACTED**", out)
    out = _HEADER_SECRET.sub(lambda m: f"{m.group(1)}: **REDACTED**", out)
    out = _KV_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}**REDACTED**", out)
    out = out.replace("\n", " ").strip()
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


def sanitize_error(text: str, *, max_len: int = 500) -> str:
    """Sanitize exception/SSH error text for last_error sensor and logs."""
    if not text:
        return ""
    out = redact_text(text, max_len=max_len * 2)
    out = _ERROR_USER_AT.sub(r"\1***", out)
    out = out.replace("\n", " ").strip()
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out
