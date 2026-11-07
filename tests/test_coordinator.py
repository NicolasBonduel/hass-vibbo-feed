"""Tests for the Vibbo coordinator against a local GraphQL server.

These use a real HTTP server rather than aioclient_mock, which replaces Home
Assistant's client sessions and so hides cookie jar and session lifecycle bugs.
"""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vibbo.const import DOMAIN
from custom_components.vibbo.coordinator import VibboDataCoordinator
from custom_components.vibbo.session import async_get_vibbo_session

STORED_COOKIE = "sesid=stored; sesid.sig=storedsig"
ITEM = {"happenedAt": "2026-11-06T09:46:11.436Z"}


@pytest.fixture
async def vibbo_server(aiohttp_server, socket_enabled):
    """Serve GraphQL the way vibbo.no does for a given session state.

    Like vibbo.no, every response sets a new anonymous sesid cookie. The
    server records which sesid each request carried.
    """
    state = {"stream": {"items": [ITEM]}, "viewer": {"id": "1"}, "received": []}

    async def graphql(request: web.Request) -> web.Response:
        state["received"].append(request.cookies.get("sesid"))
        if request.query["name"] == "vibboActivityStream":
            data = {"stream": state["stream"]}
        else:
            data = {"viewer": state["viewer"]}
        response = web.json_response({"data": data})
        response.set_cookie("sesid", "e30=")
        return response

    app = web.Application()
    app.router.add_post("/graphql", graphql)
    server = await aiohttp_server(app)
    base = str(server.make_url("")).rstrip("/")
    with (
        patch(
            "custom_components.vibbo.coordinator.GRAPHQL_URL",
            f"{base}/graphql?name=vibboActivityStream",
        ),
        patch("custom_components.vibbo.auth.VIBBO_BASE", base),
        patch("custom_components.vibbo._async_register_card", AsyncMock()),
    ):
        yield state


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="brl-a",
        title="Brl A",
        data={
            "cookie": STORED_COOKIE,
            "organization_id": "T3Jn",
            "organization_slug": "brl-a",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_returns_stream_items(hass: HomeAssistant, vibbo_server) -> None:
    """A logged-in session returns the activity stream."""
    coordinator = VibboDataCoordinator(hass, _add_entry(hass))

    assert await coordinator._async_update_data() == [ITEM]


async def test_expired_session_raises_auth_failed(
    hass: HomeAssistant, vibbo_server
) -> None:
    """A null stream for a logged-out session asks for reauthentication."""
    vibbo_server["stream"] = None
    vibbo_server["viewer"] = None
    coordinator = VibboDataCoordinator(hass, _add_entry(hass))

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_lost_organization_access_raises_update_failed(
    hass: HomeAssistant, vibbo_server
) -> None:
    """A null stream for a logged-in session is not an auth problem."""
    vibbo_server["stream"] = None
    coordinator = VibboDataCoordinator(hass, _add_entry(hass))

    with pytest.raises(UpdateFailed, match="no longer has access"):
        await coordinator._async_update_data()



async def test_session_ignores_set_cookie(hass: HomeAssistant, vibbo_server) -> None:
    """Vibbo's anonymous Set-Cookie must not replace the stored session.

    With a cookie jar, aiohttp sends a stored cookie instead of the one in an
    explicit Cookie header, so every request after a logged-out response
    would be anonymous.
    """
    coordinator = VibboDataCoordinator(hass, _add_entry(hass))

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert isinstance(async_get_vibbo_session(hass).cookie_jar, aiohttp.DummyCookieJar)
    assert vibbo_server["received"] == ["stored", "stored"]

async def test_failed_setup_leaves_usable_session(
    hass: HomeAssistant, vibbo_server
) -> None:
    """Reauth after a failed setup must not reuse the session HA closed.

    A session created during entry setup is closed when the entry unloads.
    """
    vibbo_server["stream"] = None
    vibbo_server["viewer"] = None
    entry = _add_entry(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert not async_get_vibbo_session(hass).closed
