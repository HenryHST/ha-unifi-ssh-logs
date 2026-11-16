"""Diagnostics for UniFi SSH Logs (redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_KEY_PATH, CONF_PRIVATE_KEY, DOMAIN, PUBLIC_SAMPLE_LEN
from .coordinator import UnifiSshLogsCoordinator
from .sanitize import redact_text, sanitize_error

_REDACT = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry without secrets."""
    coordinator: UnifiSshLogsCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    merged = {**entry.data, **entry.options}
    safe_config = dict(merged)
    if CONF_PASSWORD in safe_config:
        safe_config[CONF_PASSWORD] = _REDACT if safe_config[CONF_PASSWORD] else None
    if CONF_PRIVATE_KEY in safe_config and safe_config[CONF_PRIVATE_KEY]:
        safe_config[CONF_PRIVATE_KEY] = _REDACT
        safe_config["private_key_configured"] = True
    else:
        safe_config["private_key_configured"] = False
    if CONF_KEY_PATH in safe_config and safe_config[CONF_KEY_PATH]:
        # Keep path shape, redact filename contents implication
        safe_config[CONF_KEY_PATH] = str(safe_config[CONF_KEY_PATH])
        safe_config["key_configured"] = True
    else:
        safe_config["key_configured"] = False

    data: dict[str, Any] = {
        "config": safe_config,
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "version": entry.version,
            "unique_id": entry.unique_id,
        },
    }
    if coordinator is None:
        return data

    snap = coordinator.data
    data["status"] = {
        "status": snap.status,
        "last_fetch": snap.last_fetch.isoformat() if snap.last_fetch else None,
        "last_error": sanitize_error(snap.last_error or "", max_len=200),
        "open_alerts": snap.open_alerts,
        "match_count_total": snap.match_count_total,
        "last_files": list(snap.last_files),
        "rules": [r.id for r in snap.rules],
        "alert_history": [
            {
                "rule_id": h.get("rule_id"),
                "severity": h.get("severity"),
                "matched_at": h.get("matched_at"),
                "message": redact_text(
                    str(h.get("message") or ""), max_len=PUBLIC_SAMPLE_LEN
                ),
            }
            for h in snap.alert_history[:10]
        ],
        "active_alerts": [
            rid for rid, st in snap.alert_states.items() if st.active
        ],
    }
    return data
