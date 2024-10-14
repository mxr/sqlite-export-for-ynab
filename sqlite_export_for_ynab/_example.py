from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp


@dataclass
class Client:
    session: aiohttp.ClientSession

    async def __call__(self) -> str:
        async with self.session.get(
            "https://jsonplaceholder.typicode.com/todos/1"
        ) as resp:
            return await resp.text()


async def call() -> str:
    async with aiohttp.ClientSession() as session:
        return await Client(session)()


asyncio.run(call())
