"""Shared fixtures for the Vibbo tests."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load integrations from custom_components."""
    yield


@pytest.fixture(autouse=True)
def skip_frontend_dependencies(hass):
    """Mark manifest dependencies as loaded.

    The frontend needs the hass_frontend package, which the test harness does
    not install, and the card registration it serves is patched out anyway.
    """
    hass.config.components.update({"frontend", "http", "lovelace"})
