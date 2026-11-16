"""UniFi SSH Logs integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CUSTOM_RULES_PATH,
    CONF_ENABLE_PARSING,
    CONF_FETCH_JOURNAL,
    CONF_FETCH_MESSAGES,
    CONF_FETCH_UNIFI,
    CONF_KEY_PATH,
    CONF_KNOWN_HOSTS,
    CONF_OUT_DIR,
    CONF_RETENTION_MAX_AGE_DAYS,
    CONF_RETENTION_MAX_FILES,
    CONF_SCAN_INTERVAL,
    DEFAULT_CUSTOM_RULES_PATH,
    DEFAULT_HOST,
    DEFAULT_KNOWN_HOSTS,
    DEFAULT_OUT_DIR,
    DEFAULT_RETENTION_MAX_AGE_DAYS,
    DEFAULT_RETENTION_MAX_FILES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_SCAN_SECONDS,
    SERVICE_FETCH,
    STATUS_IDLE,
)
from .coordinator import CoordinatorData, UnifiSshLogsCoordinator, load_asyncssh_blocking
from .http import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
                vol.Optional(CONF_KEY_PATH): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_KNOWN_HOSTS, default=DEFAULT_KNOWN_HOSTS): cv.string,
                vol.Optional(CONF_OUT_DIR, default=DEFAULT_OUT_DIR): cv.string,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_SECONDS)),
                vol.Optional(CONF_ENABLE_PARSING, default=True): cv.boolean,
                vol.Optional(
                    CONF_CUSTOM_RULES_PATH, default=DEFAULT_CUSTOM_RULES_PATH
                ): cv.string,
                vol.Optional(CONF_FETCH_MESSAGES, default=True): cv.boolean,
                vol.Optional(CONF_FETCH_JOURNAL, default=True): cv.boolean,
                vol.Optional(CONF_FETCH_UNIFI, default=True): cv.boolean,
                vol.Optional(
                    CONF_RETENTION_MAX_FILES, default=DEFAULT_RETENTION_MAX_FILES
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
                vol.Optional(
                    CONF_RETENTION_MAX_AGE_DAYS,
                    default=DEFAULT_RETENTION_MAX_AGE_DAYS,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_FETCH_SCHEMA = vol.Schema(
    {
        vol.Optional("mode", default="logs"): vol.In(
            ("logs", "messages", "journal", "unifi", "support", "all")
        ),
        vol.Optional("include_support", default=False): cv.boolean,
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from configuration.yaml (supports !secret for password)."""
    conf = config.get(DOMAIN)
    if not conf:
        return True

    data = dict(conf)
    data.setdefault(CONF_KEY_PATH, "")

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=data,
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi SSH Logs from a config entry."""
    # Preload asyncssh off the loop (first import does blocking disk I/O).
    await hass.async_add_executor_job(load_asyncssh_blocking)

    coordinator = UnifiSshLogsCoordinator(hass, entry)
    await hass.async_add_executor_job(coordinator.reload_rules)
    # Defer first SSH refresh until the polling switch restores (may be off).
    coordinator.async_set_updated_data(CoordinatorData(status=STATUS_IDLE))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    async_register_http_views(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_FETCH):
            hass.services.async_remove(DOMAIN, SERVICE_FETCH)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_FETCH):
        return

    async def _handle_fetch(call: ServiceCall) -> None:
        mode = call.data.get("mode", "logs")
        include_support = bool(call.data.get("include_support", False))
        entry_id = call.data.get("entry_id")
        coordinators: dict[str, UnifiSshLogsCoordinator] = hass.data.get(DOMAIN, {})
        if entry_id:
            targets = [coordinators[entry_id]] if entry_id in coordinators else []
        else:
            targets = list(coordinators.values())
        for coordinator in targets:
            data = await coordinator.async_fetch(
                mode=mode, include_support=include_support
            )
            coordinator.async_set_updated_data(data)

    hass.services.async_register(
        DOMAIN, SERVICE_FETCH, _handle_fetch, schema=SERVICE_FETCH_SCHEMA
    )
