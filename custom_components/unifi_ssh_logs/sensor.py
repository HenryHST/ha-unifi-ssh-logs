"""Status sensors for UniFi SSH Logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_ALERT_HISTORY, DOMAIN
from .coordinator import UnifiSshLogsCoordinator

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_status",
        translation_key="last_status",
        icon="mdi:lan-check",
    ),
    SensorEntityDescription(
        key="last_fetch",
        translation_key="last_fetch",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="last_error",
        translation_key="last_error",
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key="open_alerts",
        translation_key="open_alerts",
        icon="mdi:bell-badge-outline",
        native_unit_of_measurement="alerts",
    ),
    SensorEntityDescription(
        key="match_count",
        translation_key="match_count",
        icon="mdi:counter",
        native_unit_of_measurement="matches",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up status sensors."""
    coordinator: UnifiSshLogsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        UnifiSshLogsSensor(coordinator, entry, description) for description in SENSORS
    )


class UnifiSshLogsSensor(CoordinatorEntity[UnifiSshLogsCoordinator], SensorEntity):
    """Expose coordinator status fields."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiSshLogsCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
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

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the sensor value."""
        data = self.coordinator.data
        key = self.entity_description.key
        if key == "last_status":
            return data.status
        if key == "last_fetch":
            return data.last_fetch
        if key == "last_error":
            return data.last_error or "none"
        if key == "open_alerts":
            return data.open_alerts
        if key == "match_count":
            return data.match_count_total
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes."""
        key = self.entity_description.key
        if key == "last_status":
            return {"last_files": list(self.coordinator.data.last_files)}
        if key == "match_count":
            return {
                ATTR_ALERT_HISTORY: list(self.coordinator.data.alert_history),
                "open_alerts": self.coordinator.data.open_alerts,
            }
        return None
