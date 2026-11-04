from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atlassian_mcp.middleware import AtlassianCredentials, bind_credentials  # noqa: E402

SITE = "https://acme.atlassian.net"


@pytest.fixture
def creds() -> AtlassianCredentials:
    return AtlassianCredentials(site=SITE, email="jane@acme.com", api_token="tok-123")


@pytest.fixture
async def bound_creds(creds: AtlassianCredentials):
    async with bind_credentials(creds):
        yield creds
