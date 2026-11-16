"""Alert binary sensors (one per rule_id)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_LAST_MATCH,
    ATTR_MATCH_COUNT,
    ATTR_SAMPLE_LINE,
    ATTR_SEVERITY,
    DOMAIN,
)
from .coordinator import UnifiSshLogsCoordinator
from .parser import AlertState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one binary sensor per alert rule."""
    coordinator: UnifiSshLogsCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        UnifiSshLogsAlertSensor(coordinator, entry, rule.id, rule.name)
        for rule in coordinator.rules
    ]
    async_add_entities(entities)


class UnifiSshLogsAlertSensor(
    CoordinatorEntity[UnifiSshLogsCoordinator], BinarySensorEntity
):
    """Binary sensor reflecting whether a rule alert is active."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: UnifiSshLogsCoordinator,
        entry: ConfigEntry,
        rule_id: str,
        rule_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._rule_id = rule_id
        self._attr_translation_key = "alert_rule"
        self._attr_translation_placeholders = {"rule": rule_name}
        self._attr_name = rule_name
        self._attr_unique_id = f"{entry.entry_id}_alert_{rule_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"UniFi SSH Logs ({coordinator.host})",
            "manufacturer": "Ubiquiti",
            "model": "UDM / UniFi Console",
        }

    def _state(self) -> AlertState | None:
        return self.coordinator.data.alert_states.get(self._rule_id)

    @property
    def is_on(self) -> bool:
        """Return True if the alert is active."""
        state = self._state()
        return bool(state and state.active)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Rule match metadata (redacted + truncated sample)."""
        state = self._state()
        if state is None:
            return {
                ATTR_MATCH_COUNT: 0,
                ATTR_LAST_MATCH: None,
                ATTR_SAMPLE_LINE: "",
                ATTR_SEVERITY: "",
                "rule_id": self._rule_id,
            }
        return {
            ATTR_MATCH_COUNT: state.match_count,
            ATTR_LAST_MATCH: state.last_match.isoformat() if state.last_match else None,
            ATTR_SAMPLE_LINE: state.sample_line,
            ATTR_SEVERITY: state.severity,
            "rule_id": self._rule_id,
        }
