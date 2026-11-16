"""Polling enable switch for UniFi SSH Logs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiSshLogsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the polling switch."""
    coordinator: UnifiSshLogsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UnifiSshLogsPollingSwitch(coordinator, entry)])


class UnifiSshLogsPollingSwitch(
    CoordinatorEntity[UnifiSshLogsCoordinator], RestoreEntity, SwitchEntity
):
    """Toggle scheduled SSH log polling."""

    _attr_has_entity_name = True
    _attr_translation_key = "polling"
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self, coordinator: UnifiSshLogsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_polling"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"UniFi SSH Logs ({coordinator.host})",
            "manufacturer": "Ubiquiti",
            "model": "UDM / UniFi Console",
        }

    @property
    def is_on(self) -> bool:
        """Return True if polling is enabled."""
        return self.coordinator.polling_enabled

    async def async_added_to_hass(self) -> None:
        """Restore last state and apply polling interval."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        enabled = True
        if last is not None and last.state in ("on", "off"):
            enabled = last.state == "on"
        self.coordinator.set_polling_enabled(enabled)
        if enabled and self.coordinator.data.status == "idle":
            self.hass.async_create_task(self.coordinator.async_request_refresh())
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable scheduled polling."""
        self.coordinator.set_polling_enabled(True)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable scheduled polling (manual fetch still works)."""
        self.coordinator.set_polling_enabled(False)
        self.async_write_ha_state()
