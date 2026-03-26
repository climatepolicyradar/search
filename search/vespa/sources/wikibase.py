"""Minimal Wikibase client for fetching concept labels at specific timestamps."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 3
REQUEST_DELAY_SECONDS = 0.5
BATCH_SIZE = 50


class WikibaseConcept(TypedDict):
    wikibase_id: str
    preferred_label: str
    alternative_labels: list[str]
    description: str | None
    negative_labels: list[str]


def _parse_entity(wikibase_id: str, entity: dict) -> WikibaseConcept | None:
    """Parse a Wikibase entity into the fields we need."""
    preferred_label = entity.get("labels", {}).get("en", {}).get("value")
    if not preferred_label:
        logger.warning("Concept %s has no preferred label, skipping", wikibase_id)
        return None

    alternative_labels = []
    if isinstance(entity.get("aliases"), dict):
        alternative_labels = [
            alias.get("value")
            for alias in entity.get("aliases", {}).get("en", [])
            if alias.get("language") == "en"
        ]

    description = (
        entity.get("descriptions", {}).get("en", {}).get("value")
        if isinstance(entity.get("descriptions"), dict)
        else None
    )

    negative_labels: list[str] = []
    for claim in (entity.get("claims") or {}).values():
        for statement in claim:
            mainsnak = statement.get("mainsnak", {})
            if mainsnak.get("property") == "P9" and mainsnak.get("snaktype") == "value":
                negative_labels.append(mainsnak["datavalue"]["value"])

    return WikibaseConcept(
        wikibase_id=wikibase_id,
        preferred_label=preferred_label,
        alternative_labels=alternative_labels,
        description=description,
        negative_labels=negative_labels,
    )


async def _fetch_concept(
    client: httpx.AsyncClient,
    api_url: str,
    semaphore: asyncio.Semaphore,
    wikibase_id: str,
    timestamp: datetime,
    page_id: str,
) -> WikibaseConcept | None:
    """Fetch a single concept at a specific timestamp."""
    async with semaphore:
        try:
            response = await client.get(
                url=api_url,
                params={
                    "action": "query",
                    "format": "json",
                    "pageids": page_id,
                    "prop": "revisions",
                    "rvdir": "older",
                    "rvlimit": 1,
                    "rvprop": "content|ids",
                    "rvslots": "main",
                    "rvstart": timestamp.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                logger.warning("No pages returned for %s", wikibase_id)
                return None

            page = next(iter(pages.values()))
            revisions = page.get("revisions", [])
            if not revisions:
                logger.warning("No revision found for %s at %s", wikibase_id, timestamp)
                return None

            content = revisions[0].get("slots", {}).get("main", {}).get("*", "{}")
            entity = json.loads(content or "{}")
            if not entity:
                logger.warning("Empty entity for %s", wikibase_id)
                return None

            await asyncio.sleep(REQUEST_DELAY_SECONDS)
            return _parse_entity(wikibase_id, entity)

        except Exception:
            logger.warning("Failed to fetch concept %s", wikibase_id, exc_info=True)
            return None


async def _login(
    client: httpx.AsyncClient, api_url: str, username: str, password: str
) -> None:
    """Authenticate with Wikibase."""
    # Get login token
    token_resp = await client.get(
        url=api_url,
        params={
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json",
        },
    )
    token_resp.raise_for_status()
    login_token = token_resp.json()["query"]["tokens"]["logintoken"]

    # Log in
    login_resp = await client.post(
        url=api_url,
        data={
            "action": "login",
            "lgname": username,
            "lgpassword": password,
            "lgtoken": login_token,
            "format": "json",
        },
    )
    login_resp.raise_for_status()
    result = login_resp.json()
    if result.get("login", {}).get("result") != "Success":
        raise RuntimeError(f"Wikibase login failed: {result}")


async def fetch_concepts_at_timestamps(
    wikibase_id_to_timestamp: dict[str, str],
) -> list[WikibaseConcept]:
    """
    Fetch concepts from Wikibase, each at its specific timestamp.

    Args:
        wikibase_id_to_timestamp: mapping of wikibase ID -> ISO timestamp string

    Returns:
        List of WikibaseConcept dicts for successfully fetched concepts.
    """
    from search.config import (
        get_from_env_with_fallback,
        wikibase_password_ssm_key,
        wikibase_url_ssm_key,
        wikibase_username_ssm_key,
    )

    base_url = get_from_env_with_fallback("WIKIBASE_URL", wikibase_url_ssm_key)
    username = get_from_env_with_fallback(
        "WIKIBASE_USERNAME", wikibase_username_ssm_key
    )
    password = get_from_env_with_fallback(
        "WIKIBASE_PASSWORD", wikibase_password_ssm_key
    )
    if not all([base_url, username, password]):
        raise RuntimeError("Missing Wikibase credentials (checked env vars and SSM)")
    base_url = base_url.rstrip("/")
    api_url = f"{base_url}/w/api.php"

    async with httpx.AsyncClient(timeout=30) as client:
        await _login(client, api_url, username, password)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        all_concepts: list[WikibaseConcept] = []
        wikibase_ids = list(wikibase_id_to_timestamp.keys())

        # Process in batches to get entity info (page IDs)
        for i in range(0, len(wikibase_ids), BATCH_SIZE):
            batch_ids = wikibase_ids[i : i + BATCH_SIZE]

            entity_resp = await client.get(
                url=api_url,
                params={
                    "action": "wbgetentities",
                    "format": "json",
                    "ids": "|".join(batch_ids),
                    "props": "info",
                },
            )
            entity_resp.raise_for_status()
            entity_data = entity_resp.json()

            if "error" in entity_data:
                logger.warning("Error fetching batch: %s", entity_data["error"])
                continue

            # Fetch each concept's revision concurrently
            tasks = []
            for wid in batch_ids:
                entity_info = entity_data.get("entities", {}).get(wid, {})
                page_id = str(entity_info.get("pageid", ""))
                if not page_id:
                    continue

                ts_str = wikibase_id_to_timestamp[wid]
                ts = datetime.fromisoformat(ts_str).astimezone(timezone.utc)

                tasks.append(
                    _fetch_concept(client, api_url, semaphore, wid, ts, page_id)
                )

            results = await asyncio.gather(*tasks)
            for concept in results:
                if concept is not None:
                    all_concepts.append(concept)

            logger.info(
                "Batch %d/%d: fetched %d concepts",
                i // BATCH_SIZE + 1,
                (len(wikibase_ids) + BATCH_SIZE - 1) // BATCH_SIZE,
                sum(1 for c in results if c is not None),
            )

    return all_concepts


def fetch_concepts_at_timestamps_sync(
    wikibase_id_to_timestamp: dict[str, str],
) -> list[WikibaseConcept]:
    """Sync wrapper around fetch_concepts_at_timestamps."""
    return asyncio.run(fetch_concepts_at_timestamps(wikibase_id_to_timestamp))
