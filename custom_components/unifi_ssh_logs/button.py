"""Buttons for UniFi SSH Logs."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiSshLogsCoordinator

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="fetch_logs",
        translation_key="fetch_logs",
        icon="mdi:file-download-outline",
    ),
    ButtonEntityDescription(
        key="fetch_support",
        translation_key="fetch_support",
        icon="mdi:package-down",
    ),
    ButtonEntityDescription(
        key="fetch_all",
        translation_key="fetch_all",
        icon="mdi:download-multiple",
    ),
    ButtonEntityDescription(
        key="clear_alerts",
        translation_key="clear_alerts",
        icon="mdi:bell-cancel-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator: UnifiSshLogsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        UnifiSshLogsButton(coordinator, entry, description) for description in BUTTONS
    )


class UnifiSshLogsButton(CoordinatorEntity[UnifiSshLogsCoordinator], ButtonEntity):
    """Trigger fetch or clear alerts."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiSshLogsCoordinator,
        entry: ConfigEntry,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"UniFi SSH Logs ({coordinator.host})",
            "manufacturer": "Ubiquiti",
            "model": "UDM / UniFi Console",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        key = self.entity_description.key
        if key == "clear_alerts":
            self.coordinator.clear_alerts()
            return
        mode = {
            "fetch_logs": "logs",
            "fetch_support": "support",
            "fetch_all": "all",
        }[key]
        include_support = mode in ("support", "all")
        await self.coordinator.async_fetch(
            mode=mode, include_support=include_support
        )
        self.coordinator.async_set_updated_data(self.coordinator.data)
