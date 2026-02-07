"""Sensor platform for Vibbo."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ORGANIZATION_SLUG, DOMAIN
from .coordinator import VibboDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vibbo sensor from a config entry."""
    coordinator: VibboDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VibboFeedSensor(coordinator, entry)])


class VibboFeedSensor(CoordinatorEntity[VibboDataCoordinator], SensorEntity):
    """Sensor that exposes the Vibbo activity feed."""

    _attr_has_entity_name = True
    _attr_translation_key = "feed"
    _attr_icon = "mdi:newspaper-variant-outline"

    def __init__(
        self,
        coordinator: VibboDataCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_feed"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Vibbo",
            manufacturer="Vibbo",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str:
        """Return the latest item title as the sensor state."""
        if self.coordinator.data:
            title = (
                self.coordinator.data[0].get("item", {}).get("title", "No Data")
            )
            return (title[:50] + "…") if len(title) > 50 else title
        return "No Data"

    @property
    def extra_state_attributes(self) -> dict:
        """Return feed items and org slug as attributes."""
        return {
            "items": self.coordinator.data or [],
            "organization_slug": self._entry.data.get(
                CONF_ORGANIZATION_SLUG, ""
            ),
        }
