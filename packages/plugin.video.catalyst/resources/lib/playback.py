# -*- coding: utf-8 -*-
"""Glue between scraping, the Torbox resolver and the Kodi player."""
import xbmcgui

from . import kodi
from . import scrapers
from . import quality
from . import tmdb
from .resolvers import torbox


def _annotate_cached(sources):
    """Mark which sources Torbox already has, optionally drop the rest."""
    by_hash = {}
    for s in sources:
        h = torbox.hash_from_magnet(s.get('magnet', ''))
        s['_hash'] = h
        if h:
            by_hash.setdefault(h, []).append(s)
    cached = torbox.check_cached(list(by_hash.keys()))
    for s in sources:
        s['cached'] = s.get('_hash') in cached
    if kodi.get_bool('cached_only', True):
        sources = [s for s in sources if s['cached']]
    elif kodi.get_bool('cached_first', True):
        # stable sort keeps the within-group order from sort_sources()
        sources.sort(key=lambda s: 0 if s.get('cached') else 1)
    return sources


def _choose(sources):
    """Auto-play the best source or show the native selection dialog."""
    if not sources:
        return None
    if kodi.get_bool('autoplay', False):
        return sources[0]
    labels = []
    for s in sources:
        prefix = '[B]+[/B] ' if s.get('cached') else ''
        labels.append(prefix + quality.label_for(s))
    idx = kodi.select('Choose a source', labels)
    return sources[idx] if idx >= 0 else None


def _publish_now_playing(payload):
    """Hand the scrobble service the ids of what we're about to play."""
    import json
    xbmcgui.Window(10000).setProperty('catalyst.now_playing', json.dumps(payload))


_PROBE_TIMEOUT = 10      # seconds for the link-liveness check
_MAX_FAILOVER = 10       # safety cap on how many sources we try per click


def _link_ok(url):
    """Cheap liveness probe: does this resolved URL look playable?

    A HEAD (falling back to a 2-byte ranged GET for CDNs that reject HEAD) is
    enough to catch dead/expired debrid links before we commit Kodi's single
    setResolvedUrl to one. It can't catch failures that only surface inside the
    player - that needs the Player().play() loop (Tier 2).
    """
    import requests
    try:
        r = requests.head(url, timeout=_PROBE_TIMEOUT, allow_redirects=True)
        if r.status_code in (403, 405):     # some CDNs refuse HEAD
            r = requests.get(url, timeout=_PROBE_TIMEOUT, stream=True,
                             headers={'Range': 'bytes=0-1'})
            r.close()
        ctype = r.headers.get('Content-Type', '').lower()
        return r.status_code < 400 and 'text/html' not in ctype
    except Exception as exc:  # noqa: BLE001 - a probe failure just means "try next"
        kodi.log('link probe failed: {0}'.format(exc))
        return False


def _resolve_playable(sources, chosen):
    """Resolve sources to a working URL, chosen first, then the rest in rank.

    Returns the first link that both resolves and passes the liveness probe;
    falls over to the next source on any failure (unless failover is disabled,
    in which case only the chosen source is tried)."""
    if kodi.get_bool('resolve_failover', True):
        # chosen first, then continue down the ranked list, then fall back up to
        # the higher-ranked ones that were skipped (nearest-first).
        idx = next((i for i, s in enumerate(sources) if s is chosen), 0)
        queue = [chosen] + sources[idx + 1:] + list(reversed(sources[:idx]))
    else:
        queue = [chosen]
    queue = queue[:_MAX_FAILOVER]

    with kodi.Progress('Catalyst') as pd:
        for i, source in enumerate(queue, 1):
            pd.update(int(i * 100 / len(queue)),
                      'Resolving source {0}/{1}'.format(i, len(queue)))
            url = torbox.resolve(source, cached=source.get('cached', False))
            if url and _link_ok(url):
                return url
            kodi.log('Source {0}/{1} failed, trying next: {2}'.format(
                i, len(queue), (source.get('release_title') or '')[:60]))
    return None


def _play(sources, chosen, list_item, payload=None):
    url = _resolve_playable(sources, chosen)
    if not url:
        kodi.notify('No working source found')
        kodi.resolve_fail()
        return
    play_item = xbmcgui.ListItem(path=url)
    if list_item is not None:
        thumb = list_item.getArt('thumb')
        if thumb:
            play_item.setArt({'thumb': thumb, 'poster': thumb})
    if payload:
        _publish_now_playing(payload)
    kodi.resolve(url, play_item)


def play_movie(tmdb_id, list_item=None):
    details = tmdb.movie_details(tmdb_id)
    if not details:
        kodi.resolve_fail()
        return
    title = details.get('title') or details.get('original_title', '')
    year = (details.get('release_date') or '')[:4]
    imdb = (details.get('external_ids') or {}).get('imdb_id')

    with kodi.Progress('Catalyst') as pd:
        pd.update(20, 'Searching sources for {0}'.format(title))
        sources = scrapers.find_movie(title, year, imdb=imdb, tmdb=tmdb_id)
        pd.update(70, 'Checking Torbox cache')
        sources = _annotate_cached(sources)

    if not sources:
        kodi.notify('No playable sources found')
        kodi.resolve_fail()
        return
    chosen = _choose(sources)
    if not chosen:
        kodi.resolve_fail()
        return
    _play(sources, chosen, list_item, payload={'type': 'movie', 'tmdb': tmdb_id})


def play_episode(tmdb_id, season, episode, show_title, year, imdb=None, list_item=None):
    with kodi.Progress('Catalyst') as pd:
        pd.update(20, 'Searching {0} S{1}E{2}'.format(show_title, season, episode))
        sources = scrapers.find_episode(show_title, year, season, episode,
                                        imdb=imdb, tmdb=tmdb_id)
        pd.update(70, 'Checking Torbox cache')
        sources = _annotate_cached(sources)

    if not sources:
        kodi.notify('No playable sources found')
        kodi.resolve_fail()
        return
    chosen = _choose(sources)
    if not chosen:
        kodi.resolve_fail()
        return
    _play(sources, chosen, list_item, payload={'type': 'episode', 'show_tmdb': tmdb_id,
                                               'season': season, 'episode': episode})
