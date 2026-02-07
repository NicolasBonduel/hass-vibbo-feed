"""Authentication helper for Vibbo via Auth0 passwordless SMS."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

AUTH0_BASE = "https://innlogging.obos.no"
VIBBO_BASE = "https://vibbo.no"
CLIENT_ID = "XYMlspPsEnOhvvpV6plvaq6UZAT1e6IC"
AUTH0_CLIENT_HEADER = "eyJuYW1lIjoiYXV0aDAuanMiLCJ2ZXJzaW9uIjoiOS4zMC4wIn0="
REDIRECT_URI = f"{VIBBO_BASE}/auth/callback"
AUDIENCE = f"{VIBBO_BASE}/"
SCOPE = "openid email phone profile"

VIBBO_ORGANIZATIONS_QUERY = """query vibboOrganizations {
  viewer {
    id
    memberships {
      name
      roles
      obosCompanyNumber
      slug: organizationSlug
      vibboEnabled
      cluster
      __typename
    }
    __typename
  }
}"""

VIBBO_ORGANIZATION_QUERY = """query vibboOrganization($organizationSlug: OrganizationID!) {
  organization(id: $organizationSlug) {
    id
    name
    slug
    __typename
  }
}"""


class AuthError(Exception):
    """Authentication error."""


@dataclass
class Membership:
    """A Vibbo organization membership."""

    name: str
    slug: str
    org_id: str = ""
    obos_company_number: str = ""
    roles: list[str] = field(default_factory=list)


@dataclass
class AuthSession:
    """Holds state for an in-progress authentication."""

    state: str
    csrf: str
    nonce: str
    login_url: str


async def start_login(session: aiohttp.ClientSession) -> AuthSession:
    """Load the Auth0 login page to get _csrf, state, nonce and session cookies.

    Navigates vibbo.no/auth/login → innlogging.obos.no/authorize →
    innlogging.obos.no/login (HTML with SMS form).
    """
    async with session.get(
        f"{VIBBO_BASE}/auth/login",
        allow_redirects=True,
    ) as resp:
        html = await resp.text()
        final_url = str(resp.url)

    _LOGGER.debug("Login page URL: %s", final_url)

    # Extract _csrf token from the HTML
    csrf_match = (
        re.search(r'"_csrf"\s*:\s*"([^"]+)"', html)
        or re.search(r'name="_csrf"\s+value="([^"]+)"', html)
        or re.search(r'"_csrf","([^"]+)"', html)
        or re.search(r"_csrf['\"]?\s*[:=]\s*['\"]([^'\"]+)", html)
    )
    if not csrf_match:
        raise AuthError("Could not find _csrf token in login page")

    # Extract state from the URL query parameters
    parsed = urlparse(final_url)
    qs = parse_qs(parsed.query)

    state = qs.get("state", [None])[0]
    if not state:
        state_match = re.search(r'"state"\s*:\s*"([^"]+)"', html)
        if state_match:
            state = state_match.group(1)
    if not state:
        raise AuthError("Could not find state in login page")

    nonce = qs.get("nonce", [None])[0]
    if not nonce:
        nonce_match = re.search(r'"nonce"\s*:\s*"([^"]+)"', html)
        if nonce_match:
            nonce = nonce_match.group(1)
    if not nonce:
        raise AuthError("Could not find nonce in login page")

    return AuthSession(
        state=state,
        csrf=csrf_match.group(1),
        nonce=nonce,
        login_url=final_url,
    )


async def request_sms_code(
    session: aiohttp.ClientSession,
    auth_session: AuthSession,
    phone_number: str,
) -> None:
    """Request an SMS verification code via Auth0 passwordless."""
    payload = {
        "client_id": CLIENT_ID,
        "connection": "sms",
        "send": "code",
        "phone_number": phone_number,
        "authParams": {
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "audience": AUDIENCE,
            "_csrf": auth_session.csrf,
            "state": auth_session.state,
            "_intstate": "deprecated",
            "nonce": auth_session.nonce,
        },
    }

    async with session.post(
        f"{AUTH0_BASE}/passwordless/start",
        json=payload,
        headers={
            "Auth0-Client": AUTH0_CLIENT_HEADER,
            "Content-Type": "application/json",
            "Origin": AUTH0_BASE,
            "Referer": auth_session.login_url,
        },
    ) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise AuthError(f"Failed to request SMS code: {resp.status} {text}")
        _LOGGER.debug("SMS code requested successfully")


async def verify_code_and_get_cookie(
    session: aiohttp.ClientSession,
    auth_session: AuthSession,
    phone_number: str,
    verification_code: str,
) -> str:
    """Verify SMS code and follow the full redirect chain to obtain Vibbo cookies.

    Flow: POST /passwordless/verify → GET /passwordless/verify_redirect →
    302 /login/callback → 302 /authorize/resume →
    302 vibbo.no/auth/callback (sets sesid cookies) → 302 vibbo.no/organisasjoner
    """
    referer = auth_session.login_url

    # Step 1: POST /passwordless/verify
    async with session.post(
        f"{AUTH0_BASE}/passwordless/verify",
        json={
            "connection": "sms",
            "verification_code": verification_code,
            "phone_number": phone_number,
            "client_id": CLIENT_ID,
        },
        headers={
            "Auth0-Client": AUTH0_CLIENT_HEADER,
            "Content-Type": "application/json",
            "Origin": AUTH0_BASE,
            "Referer": referer,
        },
    ) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise AuthError(f"Verification failed: {resp.status} {text}")

    # Step 2: GET /passwordless/verify_redirect — follows the full redirect chain
    async with session.get(
        f"{AUTH0_BASE}/passwordless/verify_redirect",
        params={
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "audience": AUDIENCE,
            "_csrf": auth_session.csrf,
            "state": auth_session.state,
            "_intstate": "deprecated",
            "protocol": "oauth2",
            "nonce": auth_session.nonce,
            "connection": "sms",
            "phone_number": phone_number,
            "verification_code": verification_code,
            "auth0Client": AUTH0_CLIENT_HEADER,
        },
        headers={"Referer": referer},
        allow_redirects=True,
    ) as resp:
        _LOGGER.debug("Final redirect URL after verify: %s", resp.url)

    # Extract Vibbo session cookies from the cookie jar
    sesid = None
    sesid_sig = None
    for cookie in session.cookie_jar:
        if cookie.key == "sesid":
            sesid = cookie.value
        elif cookie.key == "sesid.sig":
            sesid_sig = cookie.value

    if not sesid or not sesid_sig:
        raise AuthError("Failed to obtain Vibbo session cookies after login")

    return f"sesid={sesid}; sesid.sig={sesid_sig}"


async def _graphql(
    session: aiohttp.ClientSession,
    cookie: str,
    operation_name: str,
    query: str,
    variables: dict | None = None,
) -> dict:
    """Execute a Vibbo GraphQL query."""
    async with session.post(
        f"{VIBBO_BASE}/graphql?name={operation_name}",
        json={
            "operationName": operation_name,
            "variables": variables or {},
            "query": query,
        },
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
            "apollo-require-preflight": "true",
        },
    ) as resp:
        if resp.status != 200:
            raise AuthError(
                f"GraphQL query {operation_name} failed: {resp.status}"
            )
        data = await resp.json()
        if "errors" in data:
            msg = data["errors"][0].get("message", str(data["errors"]))
            raise AuthError(f"GraphQL error: {msg}")
        return data


async def fetch_organizations(
    session: aiohttp.ClientSession,
    cookie: str,
) -> list[Membership]:
    """Fetch the user's Vibbo organizations via GraphQL."""
    data = await _graphql(
        session, cookie, "vibboOrganizations", VIBBO_ORGANIZATIONS_QUERY
    )

    viewer = data.get("data", {}).get("viewer")
    if not viewer:
        raise AuthError("No viewer data in response")

    memberships = []
    for m in viewer.get("memberships", []):
        if m.get("vibboEnabled"):
            memberships.append(
                Membership(
                    name=m["name"],
                    slug=m["slug"],
                    obos_company_number=m.get("obosCompanyNumber", ""),
                    roles=m.get("roles", []),
                )
            )

    if not memberships:
        raise AuthError("No Vibbo-enabled organizations found for this account")

    return memberships


async def fetch_organization_id(
    session: aiohttp.ClientSession,
    cookie: str,
    slug: str,
) -> str:
    """Fetch the base64 organization ID (e.g. T3JnYW5pemF0aW9uOi0...) for a slug."""
    data = await _graphql(
        session,
        cookie,
        "vibboOrganization",
        VIBBO_ORGANIZATION_QUERY,
        {"organizationSlug": slug},
    )

    org = data.get("data", {}).get("organization")
    if not org:
        raise AuthError(f"Could not find organization for slug: {slug}")

    org_id = org.get("id")
    if not org_id:
        raise AuthError(f"Organization has no ID: {slug}")

    return org_id
