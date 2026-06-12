# -*- coding: utf-8 -*-
"""Torbox debrid resolver.

Flow: check which magnets are cached -> add the chosen magnet -> read its file
list -> ask Torbox for a direct download link to the best video file -> play.
"""
import re
import time

import requests

from .. import kodi
from .. import cache

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
    try:
        r = requests.post('{0}/torrents/createtorrent'.format(BASE),
                          headers=_headers(),
                          data={'magnet': magnet, 'seed': 3, 'allow_zip': 'false'},
                          timeout=25)
        data = r.json().get('data') or {}
        return data.get('torrent_id') or data.get('queued_id')
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Torbox createtorrent failed: {0}'.format(exc))
        return None


def _get_torrent(torrent_id):
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
    try:
        r = requests.get('{0}/torrents/requestdl'.format(BASE),
                         params={'token': _api_key(), 'torrent_id': torrent_id,
                                 'file_id': file_id, 'redirect': 'false'},
                         timeout=20)
        return r.json().get('data')
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Torbox requestdl failed: {0}'.format(exc))
        return None


def resolve(source):
    """Turn a source dict into a directly playable URL, or None on failure."""
    if not is_configured():
        kodi.notify('Set your Torbox API key in settings')
        return None

    magnet = source.get('magnet')
    if not magnet and source.get('url', '').startswith('magnet:'):
        magnet = source['url']
    if not magnet:
        kodi.log_error('Torbox: source has no magnet (direct torrents unsupported in v1)')
        return None

    torrent_id = _add_magnet(magnet)
    if not torrent_id:
        return None

    # Cached torrents become available almost immediately; poll briefly.
    torrent = None
    for _ in range(10):
        torrent = _get_torrent(torrent_id)
        if torrent and (torrent.get('download_present') or torrent.get('download_finished')):
            break
        time.sleep(1.5)

    if not torrent:
        return None
    if not (torrent.get('download_present') or torrent.get('download_finished')):
        kodi.notify('Source not cached on Torbox yet - try another')
        return None

    best = _best_video_file(torrent.get('files') or [])
    if not best:
        kodi.log_error('Torbox: no video file in torrent {0}'.format(torrent_id))
        return None

    return _request_link(torrent_id, best.get('id'))
