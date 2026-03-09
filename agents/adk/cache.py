#!/usr/bin/env python3
"""Shared file-based caching for A2A sub-agents."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Callable, Dict, Optional


def cached_run(
    source_name: str,
    query: str,
    runner_fn: Callable[[str], Dict[str, Any]],
    data_dir: str,
    ttl: int = 600,
    cache_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a function with file-based caching.

    Args:
        source_name: Name used in the cache key prefix (e.g. "caclub").
        query: The query string to cache on.
        runner_fn: Function that takes the query and returns a dict payload.
        data_dir: Directory to store cache files.
        ttl: Cache time-to-live in seconds (default 600).
        cache_prefix: Optional prefix for cache key hash input.

    Returns:
        Cached or freshly computed result dict.
    """
    os.makedirs(data_dir, exist_ok=True)
    hash_input = f"{cache_prefix}:{query}" if cache_prefix else query
    cache_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    cache_path = os.path.join(data_dir, f"{source_name}_cache_{cache_key}.json")

    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < ttl):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    payload = runner_fn(query)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    return payload
