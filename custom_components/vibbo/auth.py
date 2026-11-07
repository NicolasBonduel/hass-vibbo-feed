"""Authentication helper for Vibbo via a pasted browser session cookie."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import aiohttp

_LOGGER = logging.getLogger(__name__)

VIBBO_BASE = "https://vibbo.no"

# Matches the cookie wherever it appears in a pasted Cookie header, cURL
# command or "name=value" pair. \b stops "sesid" matching inside "xsesid".
_SESID_RE = re.compile(r"\bsesid=([^;\s'\"^\\]+)")
_SESID_SIG_RE = re.compile(r"\bsesid\.sig=([^;\s'\"^\\]+)")

VIBBO_VIEWER_QUERY = """query vibboViewer {
  viewer {
    id
  }
}"""

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


class InvalidCookie(AuthError):
    """The pasted text does not contain the Vibbo session cookies."""


class NotLoggedIn(AuthError):
    """The session cookie is expired or belongs to a logged-out session."""


@dataclass
class Membership:
    """A Vibbo organization membership."""

    name: str
    slug: str
    org_id: str = ""
    obos_company_number: str = ""
    roles: list[str] = field(default_factory=list)


def parse_cookie(text: str) -> str:
    """Extract sesid and sesid.sig from pasted text into a Cookie header value.

    Accepts a raw Cookie header, a "Copy as cURL" command from the browser's
    network tab, or the two name=value pairs on their own.
    """
    sesid = _SESID_RE.search(text)
    sesid_sig = _SESID_SIG_RE.search(text)
    if not sesid or not sesid_sig:
        raise InvalidCookie("Could not find sesid and sesid.sig in the pasted text")
    return f"sesid={sesid.group(1)}; sesid.sig={sesid_sig.group(1)}"


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


async def is_logged_in(session: aiohttp.ClientSession, cookie: str) -> bool:
    """Return whether the cookie belongs to a logged-in Vibbo session.

    Vibbo answers logged-out sessions with null data rather than an error.
    """
    data = await _graphql(session, cookie, "vibboViewer", VIBBO_VIEWER_QUERY)
    return bool((data.get("data") or {}).get("viewer"))


async def fetch_organizations(
    session: aiohttp.ClientSession,
    cookie: str,
) -> list[Membership]:
    """Fetch the user's Vibbo organizations via GraphQL."""
    data = await _graphql(
        session, cookie, "vibboOrganizations", VIBBO_ORGANIZATIONS_QUERY
    )

    viewer = (data.get("data") or {}).get("viewer")
    if not viewer:
        raise NotLoggedIn("Vibbo session is not logged in")

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
