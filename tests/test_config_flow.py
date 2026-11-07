"""Tests for the Vibbo config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vibbo.auth import Membership, NotLoggedIn
from custom_components.vibbo.const import DOMAIN

COOKIE = "sesid=abc; sesid.sig=def"
CURL = "curl 'https://vibbo.no/' -b 'x=1; sesid=abc; sesid.sig=def'"
BRL_A = Membership(name="Brl A", slug="brl-a")
BRL_B = Membership(name="Brl B", slug="brl-b")
FLOW = "custom_components.vibbo.config_flow"


def _patch_organizations(memberships=None, error=None):
    return patch(
        f"{FLOW}.fetch_organizations",
        AsyncMock(return_value=memberships, side_effect=error),
    )


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="brl-a",
        title="Brl A",
        data={
            "cookie": "sesid=old; sesid.sig=old",
            "organization_id": "T3Jn",
            "organization_slug": "brl-a",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_user_flow_with_one_organization(hass: HomeAssistant) -> None:
    """A single membership skips the picker and stores only the session cookies."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        _patch_organizations([BRL_A]),
        patch(f"{FLOW}.fetch_organization_id", AsyncMock(return_value="T3Jn")),
        patch("custom_components.vibbo.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"cookie": CURL}
        )
        assert result["step_id"] == "options"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"scan_interval": 15}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "cookie": COOKIE,
        "organization_id": "T3Jn",
        "organization_slug": "brl-a",
    }
    assert result["options"] == {"scan_interval": 15}


async def test_user_flow_with_several_organizations(hass: HomeAssistant) -> None:
    """Several memberships lead to the organization picker."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with _patch_organizations([BRL_A, BRL_B]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"cookie": COOKIE}
        )

    assert result["step_id"] == "select_organization"


async def test_user_flow_reports_unusable_session(hass: HomeAssistant) -> None:
    """Missing cookies and logged-out sessions get their own errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cookie": "no session here"}
    )
    assert result["errors"] == {"base": "invalid_cookie"}

    with _patch_organizations(error=NotLoggedIn("logged out")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"cookie": COOKIE}
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_replaces_cookie_for_same_organization(
    hass: HomeAssistant,
) -> None:
    """Reauth rejects another account's session and stores a matching one."""
    entry = _add_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with _patch_organizations([BRL_B]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"cookie": COOKIE}
        )
    assert result["errors"] == {"base": "wrong_account"}

    with (
        _patch_organizations([BRL_A, BRL_B]),
        patch("custom_components.vibbo.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"cookie": CURL}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["cookie"] == COOKIE
