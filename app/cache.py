"""Tiny cache layer for the public catalog.

Invalidation strategy: *versioned keys*. Every cached list/detail key embeds a
namespace version number ("animals"). Any write that changes catalog data calls
bump("animals"), which INCRs the version; old keys become unreachable and expire
via TTL. This avoids scanning/deleting keys and is safe across many app servers.

The Redis backend fails open: if Redis is down, requests fall through to MySQL.
"""
import json
import logging
import time

from flask import current_app

log = logging.getLogger(__name__)


class NullBackend:
    def get(self, key):
        return None

    def set(self, key, value, ttl):
        pass

    def incr(self, key):
        return 0


class MemoryBackend:
    """Process-local cache; used for tests and single-process demos."""

    def __init__(self):
        self._data = {}

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and expires < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl):
        self._data[key] = (value, time.time() + ttl)

    def incr(self, key):
        current = int(self._data.get(key, ("0", None))[0]) + 1
        self._data[key] = (str(current), None)
        return current


class RedisBackend:
    def __init__(self, url):
        import redis

        self._redis = redis
        self._client = redis.Redis.from_url(
            url, decode_responses=True, socket_timeout=0.5, socket_connect_timeout=0.5
        )

    def get(self, key):
        try:
            return self._client.get(key)
        except self._redis.RedisError as exc:
            log.warning("Redis GET failed (falling back to DB): %s", exc)
            return None

    def set(self, key, value, ttl):
        try:
            self._client.set(key, value, ex=ttl)
        except self._redis.RedisError as exc:
            log.warning("Redis SET failed: %s", exc)

    def incr(self, key):
        try:
            return self._client.incr(key)
        except self._redis.RedisError as exc:
            log.warning("Redis INCR failed (entries expire via TTL): %s", exc)
            return 0


def init_app(app):
    kind = app.config.get("CACHE_BACKEND", "none")
    if kind == "redis":
        backend = RedisBackend(app.config["REDIS_URL"])
    elif kind == "memory":
        backend = MemoryBackend()
    else:
        backend = NullBackend()
    app.extensions["pawtrack_cache"] = backend


def _backend():
    return current_app.extensions["pawtrack_cache"]


def version(namespace):
    raw = _backend().get(f"ver:{namespace}")
    return int(raw) if raw else 0


def bump(namespace):
    _backend().incr(f"ver:{namespace}")


def get_json(key):
    raw = _backend().get(key)
    return json.loads(raw) if raw is not None else None


def set_json(key, value, ttl=None):
    ttl = ttl or current_app.config["CACHE_TTL_SECONDS"]
    _backend().set(key, json.dumps(value), ttl)
