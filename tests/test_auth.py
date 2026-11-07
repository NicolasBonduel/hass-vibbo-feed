"""Tests for parsing a pasted Vibbo session."""

import pytest

from custom_components.vibbo.auth import InvalidCookie, parse_cookie

SESID = "s%3AabcDEF123.xyz-_"
SIG = "Zm9vYmFy_-x"
EXPECTED = f"sesid={SESID}; sesid.sig={SIG}"


@pytest.mark.parametrize(
    "pasted",
    [
        pytest.param(
            f"curl 'https://vibbo.no/graphql' \\\n  -H 'accept: */*' \\\n"
            f"  -b 'ajs_id=1; sesid={SESID}; sesid.sig={SIG}; other=2'",
            id="chrome-curl-b",
        ),
        pytest.param(
            f"curl 'https://vibbo.no/' -H 'cookie: sesid={SESID}; sesid.sig={SIG}'",
            id="chrome-curl-header",
        ),
        pytest.param(
            f"curl 'https://vibbo.no/' -H 'Cookie: _ga=1; sesid={SESID}; "
            f"sesid.sig={SIG}; last_used_organization_id=x'",
            id="firefox-curl-header",
        ),
        pytest.param(
            f'curl ^"https://vibbo.no/^" -b ^"sesid={SESID}; sesid.sig={SIG}^"',
            id="windows-cmd-curl",
        ),
        pytest.param(f"sesid={SESID}; sesid.sig={SIG}", id="cookie-header"),
        pytest.param(f"Cookie: sesid.sig={SIG}; sesid={SESID}", id="reversed"),
        pytest.param(f"sesid={SESID}\nsesid.sig={SIG}\n", id="two-lines"),
    ],
)
def test_parse_cookie_extracts_session(pasted):
    """Both session cookies are found in every common paste format."""
    assert parse_cookie(pasted) == EXPECTED


@pytest.mark.parametrize(
    "pasted",
    [
        pytest.param("", id="empty"),
        pytest.param(f"sesid={SESID}", id="missing-signature"),
        pytest.param(f"xsesid={SESID}; xsesid.sig={SIG}", id="similar-names"),
    ],
)
def test_parse_cookie_rejects_incomplete_session(pasted):
    """Pastes without both session cookies are rejected."""
    with pytest.raises(InvalidCookie):
        parse_cookie(pasted)
