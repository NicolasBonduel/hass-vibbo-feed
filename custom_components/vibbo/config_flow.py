"""Config flow for Vibbo."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .auth import (
    VIBBO_BASE,
    AuthError,
    InvalidCookie,
    Membership,
    NotLoggedIn,
    fetch_organization_id,
    fetch_organizations,
    parse_cookie,
)
from .const import (
    CONF_COOKIE,
    CONF_ORGANIZATION_ID,
    CONF_ORGANIZATION_SLUG,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .session import async_get_vibbo_session

_LOGGER = logging.getLogger(__name__)

COOKIE_SCHEMA = vol.Schema(
    {vol.Required(CONF_COOKIE): TextSelector(TextSelectorConfig(multiline=True))}
)


class VibboConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vibbo."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VibboOptionsFlow:
        """Get the options flow for this handler."""
        return VibboOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._cookie: str | None = None
        self._memberships: list[Membership] = []
        self._selected_membership: Membership | None = None

    async def _validate_cookie(
        self, pasted: str, errors: dict[str, str]
    ) -> str | None:
        """Parse the pasted cookie and load its memberships, or set an error."""
        try:
            cookie = parse_cookie(pasted)
            self._memberships = await fetch_organizations(
                async_get_vibbo_session(self.hass), cookie
            )
        except InvalidCookie:
            errors["base"] = "invalid_cookie"
        except NotLoggedIn:
            errors["base"] = "invalid_auth"
        except AuthError as err:
            _LOGGER.error("Error validating Vibbo cookie: %s", err)
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating Vibbo cookie")
            errors["base"] = "unknown"
        else:
            return cookie
        return None

    async def _create_entry_for_membership(
        self, membership: Membership, scan_interval: int = DEFAULT_SCAN_INTERVAL
    ) -> ConfigFlowResult:
        """Fetch the org ID and create the config entry."""
        org_id = await fetch_organization_id(
            async_get_vibbo_session(self.hass), self._cookie, membership.slug
        )

        await self.async_set_unique_id(membership.slug)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=membership.name,
            data={
                CONF_COOKIE: self._cookie,
                CONF_ORGANIZATION_ID: org_id,
                CONF_ORGANIZATION_SLUG: membership.slug,
            },
            options={
                CONF_SCAN_INTERVAL: scan_interval,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Paste the Vibbo session cookie."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._cookie = await self._validate_cookie(
                user_input[CONF_COOKIE], errors
            )
            if self._cookie:
                # If only one org, skip the selection step
                if len(self._memberships) == 1:
                    self._selected_membership = self._memberships[0]
                    return await self.async_step_options()
                return await self.async_step_select_organization()

        return self.async_show_form(
            step_id="user",
            data_schema=COOKIE_SCHEMA,
            errors=errors,
            description_placeholders={"vibbo_url": VIBBO_BASE},
        )

    async def async_step_select_organization(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select which organization to add."""
        errors: dict[str, str] = {}

        if user_input is not None:
            slug = user_input["organization"]
            self._selected_membership = next(
                m for m in self._memberships if m.slug == slug
            )
            return await self.async_step_options()

        org_options = {m.slug: m.name for m in self._memberships}

        return self.async_show_form(
            step_id="select_organization",
            data_schema=vol.Schema(
                {
                    vol.Required("organization"): vol.In(org_options),
                }
            ),
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Configure refresh interval."""
        errors: dict[str, str] = {}

        if user_input is not None:
            scan_interval = user_input[CONF_SCAN_INTERVAL]
            membership = self._selected_membership
            try:
                return await self._create_entry_for_membership(
                    membership, scan_interval
                )
            except AuthError as err:
                _LOGGER.error("Error fetching organization: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(int, vol.Range(min=5)),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication when the stored cookie stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh cookie for the same borettslag."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            cookie = await self._validate_cookie(user_input[CONF_COOKIE], errors)
            if cookie:
                slugs = {m.slug for m in self._memberships}
                if entry.data[CONF_ORGANIZATION_SLUG] not in slugs:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_COOKIE: cookie}
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=COOKIE_SCHEMA,
            errors=errors,
            description_placeholders={"name": entry.title, "vibbo_url": VIBBO_BASE},
        )


class VibboOptionsFlow(OptionsFlow):
    """Handle Vibbo options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current
                    ): vol.All(int, vol.Range(min=5)),
                }
            ),
        )
