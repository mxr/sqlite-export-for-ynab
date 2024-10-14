from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlite_export_for_ynab._example import call
from testing.fixtures import MockResponse


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get")
async def test_call(get):
    s = '{"userId":sss 1}'
    get.return_value = MockResponse(s, 200)

    assert await call() == s
