"""Continuous traffic generator for the learning environment.

Sends a mix of POST/GET requests to the gateway so dashboards always have
data and traces are constantly flowing into Jaeger.

Env vars
--------
GATEWAY_URL   Base URL (default http://gateway:8000)
RPS           Requests per second (default 5)
SCENARIO      One of: steady (default), read_heavy, spike, write_heavy
"""

from __future__ import annotations

import asyncio
import os
import random
import time

import httpx

GATEWAY = os.getenv("GATEWAY_URL", "http://gateway:8000")
RPS = float(os.getenv("RPS", "5"))
SCENARIO = os.getenv("SCENARIO", "steady")

# action -> weight, per scenario
WEIGHTS = {
    "steady": {"create_user": 1, "create_item": 4, "search": 5, "get_item": 3},
    "read_heavy": {"create_user": 1, "create_item": 1, "search": 10, "get_item": 8},
    "write_heavy": {"create_user": 3, "create_item": 8, "search": 2, "get_item": 1},
    # 'spike' is dynamic — handled below
}

TITLES = [
    "red shoe",
    "blue hat",
    "green shirt",
    "wool socks",
    "fancy bag",
    "leather belt",
    "silk tie",
    "linen pants",
    "cotton hoodie",
]
DESCRIPTIONS = ["very nice", "limited edition", "vintage", "handmade", "imported"]


def _weights_for_tick() -> dict[str, int]:
    if SCENARIO == "spike":
        # Every 30s, spike search traffic for 10s
        in_spike = int(time.time()) % 30 < 10
        return {"create_user": 1, "create_item": 2, "search": 30 if in_spike else 5, "get_item": 3}
    return WEIGHTS.get(SCENARIO, WEIGHTS["steady"])


async def create_user(client: httpx.AsyncClient) -> str | None:
    n = random.randint(0, 99_999)
    r = await client.post(
        f"{GATEWAY}/api/users",
        json={"name": f"user_{n}", "email": f"u{n}@example.com"},
    )
    return r.json().get("id") if r.status_code == 201 else None


async def create_item(client: httpx.AsyncClient, owner_id: str) -> str | None:
    r = await client.post(
        f"{GATEWAY}/api/items",
        json={
            "title": random.choice(TITLES),
            "description": random.choice(DESCRIPTIONS),
            "owner_id": owner_id,
        },
    )
    return r.json().get("id") if r.status_code == 201 else None


async def search(client: httpx.AsyncClient) -> None:
    q = random.choice([w for t in TITLES for w in t.split()] + [""])
    await client.get(f"{GATEWAY}/api/items", params={"q": q} if q else {})


async def get_item(client: httpx.AsyncClient, item_id: str) -> None:
    await client.get(f"{GATEWAY}/api/items/{item_id}")


async def run() -> None:
    interval = 1.0 / RPS
    users: list[str] = []
    items: list[str] = []
    sent = 0
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=10) as client:
        # Wait for gateway to be reachable
        for attempt in range(60):
            try:
                r = await client.get(f"{GATEWAY}/health")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            print(f"[loadgen] waiting for gateway ({attempt + 1}/60)...")
            await asyncio.sleep(2)

        # Seed users
        for _ in range(3):
            uid = await create_user(client)
            if uid:
                users.append(uid)
        print(f"[loadgen] seeded {len(users)} users; scenario={SCENARIO}, rps={RPS}")

        while True:
            try:
                weights = _weights_for_tick()
                actions = list(weights.keys())
                action = random.choices(actions, weights=[weights[a] for a in actions])[0]

                if action == "create_user":
                    uid = await create_user(client)
                    if uid:
                        users.append(uid)
                        if len(users) > 50:
                            users.pop(0)
                elif action == "create_item" and users:
                    iid = await create_item(client, random.choice(users))
                    if iid:
                        items.append(iid)
                        if len(items) > 100:
                            items.pop(0)
                elif action == "search":
                    await search(client)
                elif action == "get_item" and items:
                    await get_item(client, random.choice(items))

                sent += 1
                if sent % 50 == 0:
                    elapsed = time.monotonic() - started
                    print(f"[loadgen] {sent} requests in {elapsed:.0f}s ({sent / elapsed:.1f}/s)")
            except Exception as exc:
                print(f"[loadgen] error: {type(exc).__name__}: {exc}")

            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(run())
