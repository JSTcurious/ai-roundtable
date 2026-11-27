"""
backend/models/discovery.py

Reads provider model-list APIs for availability, retirement dates and
aliases. Best effort: a provider that errors, has no API key, or misses the
deadline is simply absent from the result. Perplexity has no list endpoint.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, wait

import httpx

from backend.models.registry import parse_date

logger = logging.getLogger(__name__)


def _anthropic(timeout: float):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    from anthropic import Anthropic
    out = {}
    for m in Anthropic(api_key=key, timeout=timeout).models.list(limit=100):
        d = m.model_dump()
        out[d["id"]] = {"retires_at": parse_date(d.get("retires_at")), "aliases": []}
    return out


def _openai(timeout: float):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    out = {}
    for m in OpenAI(api_key=key, timeout=timeout).models.list():
        d = m.model_dump()
        out[d["id"]] = {"retires_at": parse_date(d.get("shutdown_date")), "aliases": []}
    return out


def _google(timeout: float):
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    from google import genai
    client = genai.Client(api_key=key, http_options={"timeout": int(timeout * 1000)})
    return {
        (m.name or "").removeprefix("models/"): {"retires_at": None, "aliases": []}
        for m in client.models.list()
        if m.name
    }


def _xai(timeout: float):
    key = os.getenv("GROK_API_KEY")
    if not key:
        return None
    resp = httpx.get("https://api.x.ai/v1/models",
                     headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    resp.raise_for_status()
    return {
        m["id"]: {"retires_at": None, "aliases": list(m.get("aliases") or [])}
        for m in resp.json().get("data", [])
    }


def _openrouter(timeout: float):
    resp = httpx.get("https://openrouter.ai/api/v1/models", timeout=timeout)
    resp.raise_for_status()
    return {
        m["id"]: {"retires_at": parse_date(m.get("expiration_date")), "aliases": []}
        for m in resp.json().get("data", [])
    }


FETCHERS = {
    "anthropic": _anthropic,
    "openai": _openai,
    "google": _google,
    "xai": _xai,
    "openrouter": _openrouter,
}


def discover(timeout: float = 5.0, fetchers: dict = None) -> dict:
    """
    Returns {vendor: {"available": set(ids and aliases),
                      "retires": {id: date},
                      "models": {id: {"retires_at", "aliases"}}}}
    for each vendor that answered within the deadline.
    """
    fetchers = fetchers or FETCHERS
    pool = ThreadPoolExecutor(max_workers=len(fetchers))
    futures = {pool.submit(fn, timeout): vendor for vendor, fn in fetchers.items()}
    done, not_done = wait(futures, timeout=timeout + 1)
    pool.shutdown(wait=False, cancel_futures=True)

    result = {}
    for future in done:
        vendor = futures[future]
        try:
            models = future.result()
        except Exception as exc:
            logger.warning("[discovery] %s model list unavailable: %s", vendor, exc)
            continue
        if not models:
            continue
        available = set(models)
        for info in models.values():
            available.update(info["aliases"])
        result[vendor] = {
            "available": available,
            "retires": {mid: info["retires_at"] for mid, info in models.items() if info["retires_at"]},
            "models": models,
        }
    for future in not_done:
        logger.warning("[discovery] %s model list timed out after %.0fs", futures[future], timeout)
    return result
