"""Data coordinator for Vibbo."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_COOKIE,
    CONF_ORGANIZATION_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_API_VERSION,
    DEFAULT_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GRAPHQL_QUERY,
    GRAPHQL_URL,
)

_LOGGER = logging.getLogger(__name__)


class VibboDataCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch activity data from the Vibbo GraphQL API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self._cookie = entry.data[CONF_COOKIE]
        self._org_id = entry.data[CONF_ORGANIZATION_ID]
        self._limit = entry.options.get("limit", DEFAULT_LIMIT)
        self._api_version = DEFAULT_API_VERSION

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            config_entry=entry,
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch the activity stream from Vibbo."""
        session = async_get_clientsession(self.hass)

        payload = {
            "operationName": "vibboActivityStream",
            "variables": {
                "organizationId": self._org_id,
                "limit": self._limit,
                "filter": "ALL",
            },
            "query": GRAPHQL_QUERY,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Home Assistant Vibbo Integration",
            "Cookie": self._cookie,
            "x-version": self._api_version,
        }

        try:
            async with session.post(
                GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(
                        f"Vibbo API returned HTTP {resp.status}"
                    )
                data = await resp.json()
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with Vibbo: {err}"
            ) from err

        if (
            not isinstance(data, dict)
            or "data" not in data
            or "stream" not in data.get("data", {})
        ):
            errors = data.get("errors", []) if isinstance(data, dict) else []
            if errors:
                raise UpdateFailed(
                    f"Vibbo API error: {errors[0].get('message', errors)}"
                )
            raise UpdateFailed("Invalid response from Vibbo API")

        items: list[dict[str, Any]] = data["data"]["stream"].get("items", [])
        return items
