# -*- coding: utf-8 -*-
"""Torbox debrid resolver.

Flow: check which magnets are cached -> add the chosen magnet -> read its file
list -> ask Torbox for a direct download link to the best video file -> play.
"""
import re
import time

from .. import kodi
from .. import cache

# `requests` is imported lazily per call - keeps it off the import path until a
# stream is actually being resolved. See the note in tmdb.py.

BASE = 'https://api.torbox.app/v1/api'
VIDEO_EXT = ('.mkv', '.mp4', '.avi', '.mov', '.m4v', '.ts', '.wmv', '.flv', '.mpg', '.webm')
_HASH_RE = re.compile(r'btih:([a-fA-F0-9]{40})', re.I)


def _api_key():
    return kodi.get_setting('torbox_key', '').strip()


def is_configured():
    return bool(_api_key())


def _headers():
    return {'Authorization': 'Bearer {0}'.format(_api_key())}


def hash_from_magnet(magnet):
    m = _HASH_RE.search(magnet or '')
    return m.group(1).lower() if m else None


_CACHE_TTL = 15 * 60


def check_cached(hashes):
    """Return the set of info-hashes Torbox already has cached.

    Per-hash results are cached for 15 minutes so repeated source lists don't
    re-hit the API for hashes we already classified.
    """
    hashes = [h for h in hashes if h]
    if not hashes or not is_configured():
        return set()

    cached = set()
    unknown = []
    for h in hashes:
        flag = cache.get('tb:{0}'.format(h))
        if flag is True:
            cached.add(h)
        elif flag is None:
            unknown.append(h)
    if not unknown:
        return cached

    # API accepts repeated hash params; chunk to keep the URL sane.
    import requests
    for i in range(0, len(unknown), 50):
        chunk = unknown[i:i + 50]
        try:
            r = requests.get('{0}/torrents/checkcached'.format(BASE),
                             headers=_headers(),
                             params=[('hash', h) for h in chunk] + [('format', 'list')],
                             timeout=15)
            data = r.json().get('data') or []
            if isinstance(data, dict):
                data = list(data.values())
            found = set()
            for entry in data:
                h = (entry.get('hash') if isinstance(entry, dict) else entry) or ''
                if h:
                    found.add(h.lower())
            for h in chunk:
                hit = h.lower() in found
                if hit:
                    cached.add(h)
                cache.set('tb:{0}'.format(h), hit, _CACHE_TTL)
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('Torbox checkcached failed: {0}'.format(exc))
    return cached


def _add_magnet(magnet):
    """Add a magnet and return the created-torrent data dict (or None).

    For already-cached magnets the response often already carries the file list
    and a ready flag, which lets resolve() skip the extra mylist round-trip.
    """
    import requests
    try:
        r = requests.post('{0}/torrents/createtorrent'.format(BASE),
                          headers=_headers(),
                          data={'magnet': magnet, 'seed': 3, 'allow_zip': 'false'},
                          timeout=25)
        return r.json().get('data') or {}
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Torbox createtorrent failed: {0}'.format(exc))
        return None


def _get_torrent(torrent_id):
    import requests
    try:
        r = requests.get('{0}/torrents/mylist'.format(BASE), headers=_headers(),
                         params={'id': torrent_id, 'bypass_cache': 'true'}, timeout=15)
        data = r.json().get('data')
        if isinstance(data, list):
            data = next((t for t in data if t.get('id') == torrent_id), None)
        return data
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Torbox mylist failed: {0}'.format(exc))
        return None


def _best_video_file(files):
    videos = [f for f in files
              if (f.get('short_name') or f.get('name', '')).lower().endswith(VIDEO_EXT)]
    pool = videos or files
    if not pool:
        return None
    return max(pool, key=lambda f: f.get('size', 0) or 0)


def _request_link(torrent_id, file_id):
    import requests
    try:
        r = requests.get('{0}/torrents/requestdl'.format(BASE),
                         params={'token': _api_key(), 'torrent_id': torrent_id,
                                 'file_id': file_id, 'redirect': 'false'},
                         timeout=20)
        return r.json().get('data')
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Torbox requestdl failed: {0}'.format(exc))
        return None


def _is_ready(data):
    return bool(data and (data.get('download_present') or data.get('download_finished')))


def resolve(source, cached=False):
    """Turn a source dict into a directly playable URL, or None on failure.

    Pass cached=True for sources we already confirmed are on Torbox (the only
    kind we show). Those are available the moment they're added, so we skip the
    download-wait poll and resolve in the minimum two calls: add + request link.
    """
    if not is_configured():
        kodi.notify('Set your Torbox API key in settings')
        return None

    magnet = source.get('magnet')
    if not magnet and source.get('url', '').startswith('magnet:'):
        magnet = source['url']
    if not magnet:
        kodi.log_error('Torbox: source has no magnet (direct torrents unsupported in v1)')
        return None

    created = _add_magnet(magnet)
    if not created:
        return None
    torrent_id = created.get('torrent_id') or created.get('queued_id')
    if not torrent_id:
        return None

    # Fast path: createtorrent already returned a ready file list - go straight
    # to the download link. Otherwise fetch the file list, polling only as much
    # as needed (cached sources are ready at once; uncached may be downloading).
    files = created.get('files') if _is_ready(created) else None
    if not files:
        tries, delay = (3, 0.5) if cached else (10, 1.5)
        for i in range(tries):
            torrent = _get_torrent(torrent_id)
            if _is_ready(torrent):
                files = torrent.get('files')
                break
            if i < tries - 1:
                time.sleep(delay)
        if not files:
            kodi.notify('Source not cached on Torbox yet - try another')
            return None

    best = _best_video_file(files or [])
    if not best:
        kodi.log_error('Torbox: no video file in torrent {0}'.format(torrent_id))
        return None

    return _request_link(torrent_id, best.get('id'))
