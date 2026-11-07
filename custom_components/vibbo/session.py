"""HTTP session shared by the Vibbo config flow and coordinator."""

from __future__ import annotations

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import DOMAIN

_SESSION_KEY = f"{DOMAIN}_session"


def async_get_vibbo_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Return a client session that never stores cookies.

    Vibbo answers a logged-out sesid with Set-Cookie for a new anonymous
    session. In a session with a cookie jar, aiohttp sends that stored cookie
    instead of the one in our Cookie header, so every later request would be
    anonymous, including the one validating a freshly pasted cookie.

    A session created while a config entry sets up is closed when that entry
    unloads, e.g. after an expired cookie fails setup, so recreate it then.
    """
    session: aiohttp.ClientSession | None = hass.data.get(_SESSION_KEY)
    if session is None or session.closed:
        session = hass.data[_SESSION_KEY] = async_create_clientsession(
            hass, cookie_jar=aiohttp.DummyCookieJar()
        )
    return session
