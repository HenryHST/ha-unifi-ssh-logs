"""Event entity mirroring unifi_ssh_logs_alert bus events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiSshLogsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the alert event entity."""
    coordinator: UnifiSshLogsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UnifiSshLogsAlertEvent(coordinator, entry)])


class UnifiSshLogsAlertEvent(
    CoordinatorEntity[UnifiSshLogsCoordinator], EventEntity
):
    """Expose alert matches as an Event entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "alert"
    _attr_event_types = ["alert"]
    _attr_icon = "mdi:bell-alert-outline"

    def __init__(
        self,
        coordinator: UnifiSshLogsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_alert_event"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"UniFi SSH Logs ({coordinator.host})",
            "manufacturer": "Ubiquiti",
            "model": "UDM / UniFi Console",
        }
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register alert callback."""
        await super().async_added_to_hass()

        @callback
        def _on_alert(data: dict[str, Any]) -> None:
            self._trigger_event("alert", data)
            self.async_write_ha_state()

        self._unsub = self.coordinator.async_on_alert(_on_alert)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister alert callback."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        await super().async_will_remove_from_hass()
