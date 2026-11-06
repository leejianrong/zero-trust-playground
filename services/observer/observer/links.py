"""The tools a learner can open, and a check for whether each one is answering."""
import asyncio

import httpx

LINKS = [
    {"id": "clinic", "name": "Clinic app", "url": "http://localhost:8081",
     "purpose": "The patient-records app as a user sees it. Add, edit and delete patients.",
     "start": "make web"},
    {"id": "headlamp", "name": "Headlamp", "url": "http://localhost:4466",
     "purpose": "The cluster as an operator sees it: pods, services, network policies. Sign in with a read-only token.",
     "start": "make headlamp-ui, then make headlamp-token"},
    {"id": "keycloak", "name": "Keycloak", "url": "http://localhost:8180",
     "purpose": "Where users sign in. The clinic realm has aisha (clinician) and bob (receptionist). Open the admin console to see sessions and events.",
     "start": "make keycloak-ui"},
    {"id": "docs", "name": "Tutorial", "url": "http://localhost:8000",
     "purpose": "How each layer works and what to try, one page per slice.",
     "start": "make docs"},
    {"id": "api", "name": "Observer API", "url": "http://localhost:8765/docs",
     "purpose": "The event stream and the attack runner behind this dashboard, for curl and scripts.",
     "start": "make observer"},
]


async def probe(url: str) -> bool:
    """Up means something answered with a non-error status. A refused connection is down."""
    try:
        async with httpx.AsyncClient(timeout=1.5, follow_redirects=True) as c:
            return (await c.get(url)).status_code < 500
    except httpx.HTTPError:
        return False


async def check(links=LINKS, probe_url=probe) -> list[dict]:
    states = await asyncio.gather(*(probe_url(link["url"]) for link in links))
    return [{**link, "up": up} for link, up in zip(links, states, strict=True)]
