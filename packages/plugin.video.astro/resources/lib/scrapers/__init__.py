# -*- coding: utf-8 -*-
"""Scraper registry.

Auto-discovers every ScraperBase subclass defined in this package, runs the
enabled ones in parallel, and returns a merged, quality-tagged source list.
"""
import importlib
import pkgutil
import threading

from . import base
from .. import kodi
from .. import cache
from .. import quality as quality_mod


def _discover():
    """Import all sibling modules and collect ScraperBase subclasses."""
    found = []
    for mod_info in pkgutil.iter_modules(__path__):
        name = mod_info.name
        if name in ('base',):
            continue
        try:
            module = importlib.import_module('{0}.{1}'.format(__name__, name))
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('Failed to import scraper {0}: {1}'.format(name, exc))
            continue
        for attr in vars(module).values():
            if (isinstance(attr, type) and issubclass(attr, base.ScraperBase)
                    and attr is not base.ScraperBase):
                found.append(attr)
    return found


def _is_enabled(cls):
    # A scraper named "foo" is toggled by the boolean setting "scraper_foo".
    setting_key = 'scraper_{0}'.format(cls.name)
    return kodi.get_bool(setting_key, default=cls.enabled)


def _run(cls, method_name, args, bucket):
    try:
        inst = cls()
        results = getattr(inst, method_name)(*args)
        for s in results or []:
            s.setdefault('source', cls.name)
            if not s.get('quality'):
                s['quality'] = quality_mod.parse_quality(s.get('release_title', ''))
        bucket.extend(results or [])
    except Exception as exc:  # noqa: BLE001 - one bad scraper must not break the rest
        kodi.log_error('Scraper {0} errored: {1}'.format(cls.name, exc))


def _gather(method_name, args):
    bucket = []
    threads = []
    timeout = kodi.get_int('scraper_timeout', 25)
    for cls in _discover():
        if not _is_enabled(cls):
            continue
        t = threading.Thread(target=_run, args=(cls, method_name, args, bucket))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout)
    return bucket


def _cached_gather(cache_key, method_name, args):
    """Return raw (quality-tagged, unsorted) sources, caching the scrape itself.

    We cache *before* applying the quality floor/limit so changing those
    settings takes effect without a re-scrape; sorting happens on every call.
    """
    hours = kodi.get_int('source_cache_hours', 12)
    if hours:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit
    raw = _gather(method_name, args)
    if hours and raw:
        cache.set(cache_key, raw, hours * 3600)
    return raw


def find_movie(title, year, imdb=None, tmdb=None):
    key = 'src:movie:{0}:{1}'.format(imdb or tmdb or title, year)
    raw = _cached_gather(key, 'scrape_movie', (title, year, imdb, tmdb))
    return quality_mod.sort_sources(raw)


def find_episode(show_title, year, season, episode, imdb=None, tmdb=None):
    key = 'src:ep:{0}:{1}x{2}'.format(imdb or tmdb or show_title, season, episode)
    raw = _cached_gather(key, 'scrape_episode', (show_title, year, season, episode, imdb, tmdb))
    return quality_mod.sort_sources(raw)


def available():
    """List (name, enabled) for the Tools screen."""
    return [(cls.name, _is_enabled(cls)) for cls in _discover()]
