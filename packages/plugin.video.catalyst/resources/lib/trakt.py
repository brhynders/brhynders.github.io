# -*- coding: utf-8 -*-
"""Trakt.tv client: device-code auth, token refresh, and the two-way sync calls.

Credentials (client id/secret) come from Settings > Services. The user token is
stored as JSON in the addon profile and refreshed automatically.
"""
import json
import os
import time

import requests

from . import kodi
from . import cache

API = 'https://api.trakt.tv'
OOB = 'urn:ietf:wg:oauth:2.0:oob'
TOKEN_FILE = os.path.join(kodi.ADDON_PROFILE, 'trakt_auth.json')

# Embedded Catalyst Trakt app credentials (app-level, not per-user).
# Optional settings overrides: trakt_client_id / trakt_client_secret.
DEFAULT_CLIENT_ID = 'a87a4a42ed04c4ac000ed7973c0fd4a4211b845add9fc5940b896c8fe84c996f'
DEFAULT_CLIENT_SECRET = '2bc1cd2b40a5e781e58a2c75d1ea45a9209dcb3cf98d6f8fbafada9d463ade2e'

TTL_LIST = 1800          # trakt lists refresh every 30 min
TTL_WATCHED = 3600       # watched overlays cached 1h


# ---------------------------------------------------------------------------
# Credentials / token storage
# ---------------------------------------------------------------------------
def _client_id():
    return (kodi.get_setting('trakt_client_id', '').strip() or DEFAULT_CLIENT_ID)


def _client_secret():
    return (kodi.get_setting('trakt_client_secret', '').strip() or DEFAULT_CLIENT_SECRET)


def has_credentials():
    return bool(_client_id() and _client_secret())


def _load():
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 - missing/corrupt == not authorised
        return {}


def _save(token):
    if not os.path.isdir(kodi.ADDON_PROFILE):
        os.makedirs(kodi.ADDON_PROFILE, exist_ok=True)
    token['expires_at'] = int(time.time()) + int(token.get('expires_in', 0))
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token, f)


def is_authorised():
    return bool(_load().get('access_token'))


def sign_out():
    token = _load()
    if token.get('access_token') and has_credentials():
        try:
            requests.post('{0}/oauth/revoke'.format(API), timeout=15, json={
                'token': token['access_token'],
                'client_id': _client_id(),
                'client_secret': _client_secret(),
            })
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('Trakt revoke failed: {0}'.format(exc))
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass
    cache.clear()


# ---------------------------------------------------------------------------
# Auth: device code flow
# ---------------------------------------------------------------------------
def _device_code():
    try:
        r = requests.post('{0}/oauth/device/code'.format(API), timeout=15,
                          json={'client_id': _client_id()})
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Trakt device/code failed: {0}'.format(exc))
        return None


def _poll_token(device_code):
    """One poll. Returns (token_dict, keep_waiting)."""
    try:
        r = requests.post('{0}/oauth/device/token'.format(API), timeout=15, json={
            'code': device_code,
            'client_id': _client_id(),
            'client_secret': _client_secret(),
        })
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Trakt device/token failed: {0}'.format(exc))
        return None, True
    if r.status_code == 200:
        return r.json(), False
    if r.status_code == 400:   # still pending
        return None, True
    # 404 invalid, 409 used, 410 expired, 418 denied, 429 slow down
    return None, r.status_code == 429


def _refresh():
    token = _load()
    if not token.get('refresh_token') or not has_credentials():
        return False
    try:
        r = requests.post('{0}/oauth/token'.format(API), timeout=15, json={
            'refresh_token': token['refresh_token'],
            'client_id': _client_id(),
            'client_secret': _client_secret(),
            'redirect_uri': OOB,
            'grant_type': 'refresh_token',
        })
        r.raise_for_status()
        _save(r.json())
        return True
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Trakt token refresh failed: {0}'.format(exc))
        return False


def _access_token():
    token = _load()
    if not token.get('access_token'):
        return None
    if token.get('expires_at', 0) - 120 < time.time():
        if _refresh():
            token = _load()
    return token.get('access_token')


# ---------------------------------------------------------------------------
# Core request
# ---------------------------------------------------------------------------
def _headers(auth=True):
    h = {
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': _client_id(),
    }
    if auth:
        tok = _access_token()
        if tok:
            h['Authorization'] = 'Bearer {0}'.format(tok)
    return h


def _request(method, path, data=None, params=None, auth=True):
    if not has_credentials():
        return None
    if auth and not _access_token():
        return None
    url = '{0}{1}'.format(API, path)
    try:
        r = requests.request(method, url, headers=_headers(auth), json=data,
                             params=params, timeout=20)
        if r.status_code == 401 and auth and _refresh():
            r = requests.request(method, url, headers=_headers(auth), json=data,
                                 params=params, timeout=20)
        if r.status_code >= 400:
            kodi.log_error('Trakt {0} {1} -> {2}'.format(method, path, r.status_code))
            return None
        return r.json() if r.text else {}
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Trakt request failed {0}: {1}'.format(path, exc))
        return None


# ---------------------------------------------------------------------------
# Pull: lists
# ---------------------------------------------------------------------------
def _cached(key, fetch, ttl):
    hit = cache.get(key)
    if hit is not None:
        return hit
    val = fetch()
    if val:
        cache.set(key, val, ttl)
    return val


def watchlist(media):
    return _cached('trakt:wl:{0}'.format(media),
                   lambda: _request('GET', '/sync/watchlist/{0}'.format(media)) or [],
                   TTL_LIST)


def collection(media):
    return _cached('trakt:col:{0}'.format(media),
                   lambda: _request('GET', '/sync/collection/{0}'.format(media)) or [],
                   TTL_LIST)


def recommendations(media):
    return _cached('trakt:rec:{0}'.format(media),
                   lambda: _request('GET', '/recommendations/{0}'.format(media),
                                    params={'limit': 40}) or [],
                   TTL_LIST)


def trending(media):
    return _cached('trakt:trend:{0}'.format(media),
                   lambda: _request('GET', '/{0}/trending'.format(media),
                                    params={'limit': 40}, auth=False) or [],
                   TTL_LIST)


def popular(media):
    return _cached('trakt:pop:{0}'.format(media),
                   lambda: _request('GET', '/{0}/popular'.format(media),
                                    params={'limit': 40}, auth=False) or [],
                   TTL_LIST)


def boxoffice():
    return _cached('trakt:boxoffice',
                   lambda: _request('GET', '/movies/boxoffice', auth=False) or [],
                   TTL_LIST)


def anticipated(media):
    return _cached('trakt:antic:{0}'.format(media),
                   lambda: _request('GET', '/{0}/anticipated'.format(media),
                                    params={'limit': 40}, auth=False) or [],
                   TTL_LIST)


def playback(media):
    """In-progress items (Continue Watching). media is 'movies' or 'episodes'."""
    return _request('GET', '/sync/playback/{0}'.format(media)) or []


def history(media):
    """Recently watched, newest first. media is 'movies' or 'episodes'."""
    return _request('GET', '/sync/history/{0}'.format(media), params={'limit': 40}) or []


def calendar(start_date, days, kind='shows'):
    """Calendar for the user's shows. kind: 'shows' (airing) or 'shows/new' (premieres)."""
    return _cached('trakt:cal:{0}:{1}:{2}'.format(kind, start_date, days),
                   lambda: _request('GET', '/calendars/my/{0}/{1}/{2}'.format(
                       kind, start_date, days)) or [],
                   TTL_WATCHED)


def my_lists():
    personal = _request('GET', '/users/me/lists') or []
    liked = _request('GET', '/users/likes/lists', params={'limit': 100}) or []
    out = []
    for lst in personal:
        out.append({'name': lst.get('name', ''), 'owner': 'me',
                    'ids': lst.get('ids', {})})
    for entry in liked:
        lst = entry.get('list', entry)
        ids = lst.get('ids', {})
        owner = (lst.get('user') or {}).get('ids', {}).get('slug', '')
        out.append({'name': lst.get('name', ''), 'owner': owner, 'ids': ids})
    return out


def list_items(owner, list_id, media):
    path = ('/users/me/lists/{0}/items/{1}'.format(list_id, media) if owner == 'me'
            else '/lists/{0}/items/{1}'.format(list_id, media))
    return _request('GET', path) or []


# ---------------------------------------------------------------------------
# Pull: watched overlays
# ---------------------------------------------------------------------------
def watched_movie_ids():
    def fetch():
        data = _request('GET', '/sync/watched/movies') or []
        ids = []
        for it in data:
            tmdb = (it.get('movie') or {}).get('ids', {}).get('tmdb')
            if tmdb:
                ids.append(tmdb)
        return ids
    return set(_cached('trakt:watched:movies', fetch, TTL_WATCHED) or [])


def watched_episode_map():
    """Return {show_tmdb: [[season, episode], ...]} for watched episodes."""
    def fetch():
        data = _request('GET', '/sync/watched/shows') or []
        out = {}
        for it in data:
            tmdb = (it.get('show') or {}).get('ids', {}).get('tmdb')
            if not tmdb:
                continue
            pairs = []
            for season in it.get('seasons', []):
                s = season.get('number')
                for ep in season.get('episodes', []):
                    pairs.append([s, ep.get('number')])
            out[str(tmdb)] = pairs
        return out
    raw = _cached('trakt:watched:shows', fetch, TTL_WATCHED) or {}
    return {k: {tuple(p) for p in v} for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------
def _movie_body(tmdb_id):
    return {'movies': [{'ids': {'tmdb': int(tmdb_id)}}]}


def _episode_body(show_tmdb, season, episode):
    return {'shows': [{'ids': {'tmdb': int(show_tmdb)}, 'seasons': [
        {'number': int(season), 'episodes': [{'number': int(episode)}]}]}]}


def _invalidate():
    for k in ('movies', 'shows'):
        cache.set('trakt:wl:{0}'.format(k), None, 1)
        cache.set('trakt:watched:{0}'.format(k), None, 1)


def add_watchlist(body):
    ok = _request('POST', '/sync/watchlist', data=body) is not None
    _invalidate()
    return ok


def remove_watchlist(body):
    ok = _request('POST', '/sync/watchlist/remove', data=body) is not None
    _invalidate()
    return ok


def add_history(body):
    ok = _request('POST', '/sync/history', data=body) is not None
    _invalidate()
    return ok


def remove_history(body):
    ok = _request('POST', '/sync/history/remove', data=body) is not None
    _invalidate()
    return ok


def watchlist_movie(tmdb_id, add=True):
    body = _movie_body(tmdb_id)
    return add_watchlist(body) if add else remove_watchlist(body)


def watched_movie(tmdb_id, add=True):
    body = _movie_body(tmdb_id)
    return add_history(body) if add else remove_history(body)


def watched_episode(show_tmdb, season, episode, add=True):
    body = _episode_body(show_tmdb, season, episode)
    return add_history(body) if add else remove_history(body)


# ---------------------------------------------------------------------------
# Scrobble (used by the background service)
# ---------------------------------------------------------------------------
def scrobble(action, payload, progress):
    """action in start|pause|stop. payload is a now-playing dict."""
    if not is_authorised():
        return
    if payload.get('type') == 'movie':
        body = {'movie': {'ids': {'tmdb': int(payload['tmdb'])}}, 'progress': progress}
    else:
        body = {'show': {'ids': {'tmdb': int(payload['show_tmdb'])}},
                'episode': {'season': int(payload['season']),
                            'number': int(payload['episode'])},
                'progress': progress}
    _request('POST', '/scrobble/{0}'.format(action), data=body)
