# -*- coding: utf-8 -*-
"""Tiny TTL cache backed by SQLite in the addon profile.

Used for TMDB responses, scraped source lists and Torbox cache-checks so we
stop hammering APIs and repeat visits are instant. Stdlib only.
"""
import json
import os
import sqlite3
import threading
import time

from . import kodi

_LOCK = threading.Lock()
_CONN = None


def _connect():
    global _CONN
    if _CONN is not None:
        return _CONN
    profile = kodi.ADDON_PROFILE
    if not os.path.isdir(profile):
        os.makedirs(profile, exist_ok=True)
    _CONN = sqlite3.connect(os.path.join(profile, 'cache.db'),
                            timeout=10, check_same_thread=False)
    _CONN.execute('CREATE TABLE IF NOT EXISTS cache '
                  '(k TEXT PRIMARY KEY, v TEXT, exp REAL)')
    _CONN.commit()
    return _CONN


def get(key):
    """Return the cached value, or None if missing/expired."""
    try:
        with _LOCK:
            row = _connect().execute(
                'SELECT v, exp FROM cache WHERE k=?', (key,)).fetchone()
        if not row:
            return None
        value, exp = row
        if exp and exp < time.time():
            return None
        return json.loads(value)
    except Exception as exc:  # noqa: BLE001 - cache must never break a feature
        kodi.log_error('cache get failed: {0}'.format(exc))
        return None


def set(key, value, ttl):  # noqa: A001 - mirrors dict-ish api on purpose
    """Store value under key for ttl seconds (ttl<=0 means never expire)."""
    try:
        exp = time.time() + ttl if ttl and ttl > 0 else 0
        payload = json.dumps(value)
        with _LOCK:
            conn = _connect()
            conn.execute('REPLACE INTO cache (k, v, exp) VALUES (?, ?, ?)',
                         (key, payload, exp))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('cache set failed: {0}'.format(exc))


def clear():
    try:
        with _LOCK:
            conn = _connect()
            conn.execute('DELETE FROM cache')
            conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('cache clear failed: {0}'.format(exc))
        return False
