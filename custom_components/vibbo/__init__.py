"""The Vibbo integration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, FRONTEND_SCRIPT_URL
from .coordinator import VibboDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

_CARD_PATH = Path(__file__).parent / "frontend" / "vibbo-feed-card.js"


def _card_url() -> str:
    """Return the card URL with a content-hash query param for cache busting."""
    try:
        file_hash = hashlib.md5(_CARD_PATH.read_bytes(), usedforsecurity=False).hexdigest()[:8]
    except OSError:
        file_hash = "0"
    return f"{FRONTEND_SCRIPT_URL}?{file_hash}"


def _ha_version_gte(version: str) -> bool:
    """Check if the running HA version is >= the given version string."""
    def _to_tuple(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split(".")[:3])

    return _to_tuple(HA_VERSION) >= _to_tuple(version)


def _get_lovelace_mode(hass: HomeAssistant) -> str:
    """Get lovelace resource mode, accounting for HA version differences."""
    lovelace = hass.data["lovelace"]
    if _ha_version_gte("2026.2.0"):
        return lovelace.resource_mode
    if _ha_version_gte("2025.2.0"):
        return lovelace.mode
    return lovelace["mode"]


def _get_lovelace_resources(hass: HomeAssistant):
    """Get lovelace resources collection, accounting for HA version differences."""
    lovelace = hass.data["lovelace"]
    if _ha_version_gte("2025.2.0"):
        return lovelace.resources
    return lovelace["resources"]


async def _async_register_card(hass: HomeAssistant) -> None:
    """Register static path and Lovelace resource for the card."""
    if not _CARD_PATH.is_file():
        _LOGGER.error(
            "Vibbo card JS not found at %s — card will not be available",
            _CARD_PATH,
        )
        return

    card_url = _card_url()

    # Register the static file path
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_SCRIPT_URL, str(_CARD_PATH), False)]
        )
        _LOGGER.debug("Registered Vibbo static path from %s", _CARD_PATH)
    except RuntimeError:
        _LOGGER.debug("Vibbo static path already registered")

    # Register as Lovelace resource (storage mode) or fall back to extra JS
    if _get_lovelace_mode(hass) != "storage":
        _LOGGER.debug("Lovelace in YAML mode, falling back to add_extra_js_url")
        add_extra_js_url(hass, FRONTEND_SCRIPT_URL)
        return

    resources = _get_lovelace_resources(hass)

    async def _try_register(now):
        """Attempt registration, retrying if resources aren't loaded yet."""
        if not resources.loaded:
            _LOGGER.debug(
                "Lovelace resources not loaded yet, retrying in 5 seconds"
            )
            async_call_later(hass, 5, _try_register)
            return

        # Check if already registered (compare path without query string)
        for item in resources.async_items():
            if item["url"].split("?")[0] == FRONTEND_SCRIPT_URL:
                if item["url"] == card_url:
                    _LOGGER.debug("Vibbo card already registered with current hash")
                    return
                # Update to new hash
                _LOGGER.debug(
                    "Updating Vibbo card resource: %s -> %s",
                    item["url"],
                    card_url,
                )
                await resources.async_update_item(
                    item["id"], {"res_type": "module", "url": card_url}
                )
                return

        _LOGGER.debug("Registering Vibbo card as Lovelace resource: %s", card_url)
        await resources.async_create_item(
            {"res_type": "module", "url": card_url}
        )

    await _try_register(0)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vibbo from a config entry."""
    coordinator = VibboDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Update coordinator interval when options change
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register frontend card (once)
    if "frontend_registered" not in hass.data[DOMAIN]:
        await _async_register_card(hass)
        hass.data[DOMAIN]["frontend_registered"] = True

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry to pick up new interval."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Vibbo config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
