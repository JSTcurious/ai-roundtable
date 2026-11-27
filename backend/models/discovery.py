"""
backend/models/discovery.py

Reads provider model-list APIs for availability, retirement dates and
aliases. Best effort: a provider that errors, has no API key, or misses the
deadline is simply absent from the result. Perplexity has no list endpoint.
"""

import json
import logging
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

from backend.models.registry import parse_date

logger = logging.getLogger(__name__)


def _get_json(url: str, timeout: float, headers: dict = None) -> dict:
    # stdlib on purpose: openai/anthropic releases no longer pull in httpx
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.load(resp)


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
    # v1beta explicitly: preview models (the Gemini seat uses them) are not served on
    # v1, which google-genai 3.x uses by default — list what the client can call.
    client = genai.Client(api_key=key, http_options={"timeout": int(timeout * 1000), "api_version": "v1beta"})
    return {
        (m.name or "").removeprefix("models/"): {"retires_at": None, "aliases": []}
        for m in client.models.list()
        if m.name
    }


def _xai(timeout: float):
    key = os.getenv("GROK_API_KEY")
    if not key:
        return None
    data = _get_json("https://api.x.ai/v1/models", timeout, {"Authorization": f"Bearer {key}"})
    return {
        m["id"]: {"retires_at": None, "aliases": list(m.get("aliases") or [])}
        for m in data.get("data", [])
    }


def _openrouter(timeout: float):
    data = _get_json("https://openrouter.ai/api/v1/models", timeout)
    return {
        m["id"]: {"retires_at": parse_date(m.get("expiration_date")), "aliases": []}
        for m in data.get("data", [])
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
