"""Config flow for Vibbo."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .auth import (
    AuthError,
    AuthSession,
    Membership,
    fetch_organization_id,
    fetch_organizations,
    request_sms_code,
    start_login,
    verify_code_and_get_cookie,
)
from .const import (
    CONF_COOKIE,
    CONF_ORGANIZATION_ID,
    CONF_ORGANIZATION_SLUG,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


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
        self._phone_number: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._auth_session: AuthSession | None = None
        self._cookie: str | None = None
        self._memberships: list[Membership] = []
        self._selected_membership: Membership | None = None

    async def _cleanup_session(self) -> None:
        """Close the aiohttp session if open."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _create_entry_for_membership(
        self, membership: Membership, scan_interval: int = DEFAULT_SCAN_INTERVAL
    ) -> ConfigFlowResult:
        """Fetch the org ID and create the config entry."""
        async with aiohttp.ClientSession() as session:
            org_id = await fetch_organization_id(
                session, self._cookie, membership.slug
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
        """Step 1: Ask for phone number, send SMS code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input["phone_number"].strip()
            if not phone.startswith("+"):
                phone = f"+47{phone}"
            self._phone_number = phone

            try:
                self._session = aiohttp.ClientSession()
                self._auth_session = await start_login(self._session)
                await request_sms_code(
                    self._session, self._auth_session, self._phone_number
                )
                return await self.async_step_verify_code()
            except AuthError as err:
                _LOGGER.error("Auth error: %s", err)
                errors["base"] = "auth_error"
                await self._cleanup_session()
            except Exception:
                _LOGGER.exception("Unexpected error during SMS request")
                errors["base"] = "unknown"
                await self._cleanup_session()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("phone_number"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_verify_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Verify SMS code, then fetch organizations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input["verification_code"].strip()
            try:
                self._cookie = await verify_code_and_get_cookie(
                    self._session,
                    self._auth_session,
                    self._phone_number,
                    code,
                )
                await self._cleanup_session()

                # Fetch available organizations
                async with aiohttp.ClientSession() as session:
                    self._memberships = await fetch_organizations(
                        session, self._cookie
                    )

                # If only one org, skip the selection step
                if len(self._memberships) == 1:
                    self._selected_membership = self._memberships[0]
                    return await self.async_step_options()

                return await self.async_step_select_organization()

            except AuthError as err:
                _LOGGER.error("Verification error: %s", err)
                if "Verification failed" in str(err):
                    errors["base"] = "invalid_code"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during verification")
                errors["base"] = "unknown"
                await self._cleanup_session()

        return self.async_show_form(
            step_id="verify_code",
            data_schema=vol.Schema(
                {
                    vol.Required("verification_code"): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "phone_number": self._phone_number or "",
            },
        )

    async def async_step_select_organization(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Select which organization to add."""
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
        """Step 4: Configure refresh interval."""
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
